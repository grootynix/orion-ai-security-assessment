import base64
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse

from .agent import FakeLLM, LanguageModel
from .models import ChatRequest, SendEmailRequest, TokenRequest, UserContext
from .store import Store
from .tools import OrionTools


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_USERS = {
    "alice@example.test": {"role": "employee", "projects": ["atlas"]},
    "bob@example.test": {"role": "employee", "projects": ["prism"]},
    "manager@example.test": {
        "role": "manager",
        "projects": ["atlas", "prism"],
    },
    "admin@example.test": {
        "role": "administrator",
        "projects": ["atlas", "prism"],
    },
}
ROLE_ORDER = {"employee": 0, "manager": 1, "administrator": 2}


def create_access_token(user: UserContext) -> str:
    payload = json.dumps(user.model_dump(), separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_access_token(token: str) -> UserContext:
    padded = token + "=" * (-len(token) % 4)
    payload = base64.urlsafe_b64decode(padded.encode())
    return UserContext.model_validate_json(payload)


def create_app(
    database_path: Path | None = None,
    data_directory: Path | None = None,
    llm: LanguageModel | None = None,
) -> FastAPI:
    configured_data = data_directory or Path(
        os.environ.get("ORION_DATA_DIR", PROJECT_ROOT / "data")
    )
    configured_data = configured_data.resolve()
    configured_database = database_path or Path(
        os.environ.get(
            "ORION_DATABASE_PATH", configured_data / "orion.sqlite3"
        )
    )
    store = Store(configured_database, configured_data)
    tools = OrionTools(store, configured_data)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        store.initialize()
        yield

    application = FastAPI(
        title="Orion Enterprise Knowledge Assistant",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.store = store
    application.state.tools = tools
    application.state.llm = llm or FakeLLM(tools)

    def current_user(
        authorization: str | None = Header(default=None),
    ) -> UserContext:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=401,
                detail="A bearer token is required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            user = decode_access_token(authorization.removeprefix("Bearer ").strip())
        except Exception as exc:
            raise HTTPException(status_code=401, detail="Invalid bearer token") from exc
        if user.email not in SYNTHETIC_USERS:
            raise HTTPException(status_code=401, detail="Unknown user")
        return user

    UserDependency = Annotated[UserContext, Depends(current_user)]

    def require_role(user: UserContext, minimum: str) -> None:
        if ROLE_ORDER[user.role] < ROLE_ORDER[minimum]:
            raise HTTPException(status_code=403, detail="Insufficient role")

    @application.get("/")
    def home() -> FileResponse:
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "orion"}

    @application.post("/api/token")
    def issue_token(request: TokenRequest) -> dict[str, str]:
        email = request.email.strip().lower()
        identity = SYNTHETIC_USERS.get(email)
        if not identity:
            raise HTTPException(status_code=401, detail="Unknown synthetic user")
        user = UserContext(email=email, **identity)
        store.write_audit(
            email,
            "/api/token",
            "issue_token",
            {"email": email},
            "success",
        )
        return {"access_token": create_access_token(user), "token_type": "bearer"}

    @application.post("/api/chat")
    def chat(request: ChatRequest, user: UserDependency) -> dict:
        try:
            response = application.state.llm.respond(request.message, user)
        except Exception as exc:
            store.write_audit(
                user.email,
                "/api/chat",
                "chat",
                {"message": request.message},
                "failure",
            )
            raise HTTPException(
                status_code=400, detail="The request could not be completed"
            ) from exc
        store.write_audit(
            user.email,
            "/api/chat",
            "chat",
            {"message": request.message},
            "success",
        )
        return response

    @application.get("/api/documents")
    def list_documents(
        user: UserDependency,
        q: str = Query(default="", max_length=300),
    ) -> list[dict]:
        documents = tools.search_documents(q, user, endpoint="/api/documents")
        return [
            {
                "id": document["id"],
                "title": document["title"],
                "classification": document["classification"],
                "project": document["project"],
            }
            for document in documents
        ]

    @application.get("/api/documents/{document_id}")
    def read_document(document_id: str, user: UserDependency) -> dict:
        document = tools.get_document(document_id, user)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return document

    @application.get("/api/customers/{customer_id}")
    def read_customer(customer_id: str, user: UserDependency) -> dict:
        customer = tools.get_customer(customer_id, user)
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        return customer

    @application.post("/api/tools/send-email")
    def send_email(request: SendEmailRequest, user: UserDependency) -> dict:
        try:
            result = tools.send_email(
                request.to,
                request.subject,
                request.body,
                user,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail="The message could not be queued"
            ) from exc
        return result

    @application.get("/api/audit")
    def read_audit(
        user: UserDependency,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[dict]:
        require_role(user, "administrator")
        return store.audit_events(limit)

    @application.get("/api/outbox")
    def read_outbox(
        user: UserDependency,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[dict]:
        require_role(user, "administrator")
        return store.outbox_messages(limit)

    return application


app = create_app()
