"""HTTP route handlers. Business logic lives in application services."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.api.deps import UserDependency
from app.api.rate_limit import client_key
from app.auth.tokens import TokenError
from app.domain_errors import OrionDomainError
from app.models import (
    ApprovalDecisionRequest,
    ChatRequest,
    SendEmailRequest,
    TokenRequest,
)
from app.tools.broker import ToolBrokerError


def _http_from_domain(exc: Exception) -> HTTPException:
    """Map domain/tool errors to safe HTTP responses without stack traces."""
    if isinstance(exc, OrionDomainError):
        return HTTPException(status_code=exc.status_code, detail=exc.message)
    if isinstance(exc, ToolBrokerError):
        return HTTPException(status_code=exc.status_code, detail=str(exc))
    if isinstance(exc, TokenError):
        return HTTPException(status_code=401, detail="Invalid bearer token")
    return HTTPException(status_code=400, detail="The request could not be completed")


def build_router() -> APIRouter:
    """Construct HTTP routes; authorization and tools stay in services/broker."""
    router = APIRouter()

    @router.get("/")
    def home() -> FileResponse:
        return FileResponse(Path(__file__).resolve().parents[1] / "static" / "index.html")

    @router.get("/health")
    def health(request: Request) -> dict[str, str]:
        settings = request.app.state.settings
        return {
            "status": "ok",
            "service": "orion",
            "environment": settings.environment,
        }

    @router.post("/api/token")
    def issue_token(request_body: TokenRequest, request: Request) -> dict[str, str]:
        settings = request.app.state.settings
        limiter = request.app.state.rate_limiter
        limiter.check(
            client_key(request, "token"),
            settings.rate_limit_token_per_minute,
            security_logger=request.app.state.security_logger,
            path="/api/token",
        )
        if settings.is_production or not settings.enable_dev_idp:
            request.app.state.security_logger.emit(
                "token_issuance_denied",
                reason="dev_idp_disabled",
            )
            raise HTTPException(
                status_code=403,
                detail="Development token issuance is disabled",
            )
        audit = request.app.state.audit
        try:
            token = request.app.state.identity_provider.issue_development_token(
                request_body.email
            )
        except TokenError as exc:
            request.app.state.security_logger.emit(
                "token_issuance_anomaly",
                reason=str(exc),
                email=request_body.email.strip().lower(),
            )
            raise HTTPException(status_code=401, detail="Unknown synthetic user") from exc
        audit.record(
            user_email=request_body.email.strip().lower(),
            endpoint="/api/token",
            tool_selected="issue_token",
            arguments={"email": request_body.email.strip().lower()},
            status="success",
            authorization_decision="dev_idp",
        )
        return {"access_token": token, "token_type": "bearer"}

    @router.post("/api/logout")
    def logout(
        user: UserDependency,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="A bearer token is required")
        token = authorization.removeprefix("Bearer ").strip()
        try:
            jti = request.app.state.token_service.extract_jti(token)
            request.app.state.revocation.revoke(jti, user.email)
        except TokenError as exc:
            raise _http_from_domain(exc) from exc
        request.app.state.audit.record(
            user_email=user.email,
            endpoint="/api/logout",
            tool_selected="revoke_token",
            arguments={"jti_redacted": True},
            status="success",
            authorization_decision="self_revoke",
        )
        return {"status": "revoked"}

    @router.post("/api/chat")
    def chat(request_body: ChatRequest, user: UserDependency, request: Request) -> dict:
        settings = request.app.state.settings
        request.app.state.rate_limiter.check(
            client_key(request, f"chat:{user.email}"),
            settings.rate_limit_api_per_minute,
            security_logger=request.app.state.security_logger,
            path="/api/chat",
            user_email=user.email,
        )
        try:
            return request.app.state.chat_service.handle(request_body.message, user)
        except Exception as exc:
            request.app.state.audit.record(
                user_email=user.email,
                endpoint="/api/chat",
                tool_selected="chat",
                arguments={"message": request_body.message},
                status="failure",
            )
            raise _http_from_domain(exc) from exc

    @router.get("/api/documents")
    def list_documents(
        user: UserDependency,
        request: Request,
        q: str = Query(default="", max_length=300),
    ) -> list[dict]:
        return request.app.state.document_service.search(q, user)

    @router.get("/api/documents/{document_id}")
    def read_document(
        document_id: str, user: UserDependency, request: Request
    ) -> dict:
        document = request.app.state.document_service.get(document_id, user)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return document

    @router.get("/api/customers/{customer_id}")
    def read_customer(
        customer_id: str, user: UserDependency, request: Request
    ) -> dict:
        customer = request.app.state.tool_implementations.get_customer(
            customer_id, user
        )
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        return customer

    @router.post("/api/tools/send-email")
    def send_email(
        request_body: SendEmailRequest, user: UserDependency, request: Request
    ) -> dict:
        request.app.state.rate_limiter.check(
            client_key(request, f"email:{user.email}"),
            min(30, request.app.state.settings.rate_limit_api_per_minute),
            security_logger=request.app.state.security_logger,
            path="/api/tools/send-email",
            user_email=user.email,
        )
        broker = request.app.state.broker
        try:
            result = broker.execute(
                "send_email",
                {
                    "to": request_body.to,
                    "subject": request_body.subject,
                    "body": request_body.body,
                },
                user,
                endpoint="/api/tools/send-email",
            )
        except ToolBrokerError as exc:
            raise HTTPException(
                status_code=exc.status_code, detail=str(exc)
            ) from exc
        if result.status == "pending_approval":
            return {
                "status": "pending_approval",
                "pending_action_id": result.pending_action_id,
            }
        return result.result

    @router.get("/api/approvals/pending")
    def list_pending_approvals(
        user: UserDependency, request: Request
    ) -> list[dict]:
        try:
            return request.app.state.approval_service.list_pending(user)
        except ToolBrokerError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.post("/api/approvals/{action_id}")
    def decide_approval(
        action_id: str,
        body: ApprovalDecisionRequest,
        user: UserDependency,
        request: Request,
    ) -> dict:
        request.app.state.rate_limiter.check(
            client_key(request, f"approvals:{user.email}"),
            min(30, request.app.state.settings.rate_limit_api_per_minute),
            security_logger=request.app.state.security_logger,
            path=f"/api/approvals/{action_id}",
            user_email=user.email,
        )
        try:
            return request.app.state.approval_service.decide(
                action_id, body.decision, user
            )
        except ToolBrokerError as exc:
            raise _http_from_domain(exc) from exc

    @router.get("/api/audit")
    def read_audit(
        user: UserDependency,
        request: Request,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[dict]:
        decision = request.app.state.authorization.can_read_audit(user)
        if not decision.allowed:
            # Detection: non-admin probing sensitive audit surface.
            request.app.state.security_logger.emit(
                "unauthorized_resource_access",
                user_email=user.email,
                resource_type="audit",
                path="/api/audit",
                reason=decision.reason,
            )
            raise HTTPException(status_code=403, detail="Insufficient role")
        return request.app.state.store.audit_events(limit)

    @router.get("/api/outbox")
    def read_outbox(
        user: UserDependency,
        request: Request,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[dict]:
        decision = request.app.state.authorization.can_read_outbox(user)
        if not decision.allowed:
            request.app.state.security_logger.emit(
                "unauthorized_resource_access",
                user_email=user.email,
                resource_type="outbox",
                path="/api/outbox",
                reason=decision.reason,
            )
            raise HTTPException(status_code=403, detail="Insufficient role")
        return request.app.state.store.outbox_messages(limit)

    return router
