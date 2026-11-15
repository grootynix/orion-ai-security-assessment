"""Concrete tool implementations with authorization and path containment."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from app.authorization.policy import AuthorizationService
from app.config.settings import Settings
from app.models import UserContext
from app.observability.audit import AuditRecorder
from app.persistence.store import Store

ALLOWED_FIXTURE_IDS = {
    "quarterly-brief": "quarterly-brief.txt",
    "legacy-sample": "legacy_sample.env",
}

ALLOWED_FIXTURE_EXTENSIONS = {".txt", ".env", ".md", ".json"}


class ToolImplementations:
    """Business-side tool handlers. Authorization is enforced here and in broker."""

    def __init__(
        self,
        store: Store,
        settings: Settings,
        authorization: AuthorizationService,
        audit: AuditRecorder,
    ):
        self.store = store
        self.settings = settings
        self.authorization = authorization
        self.audit = audit
        self.fixtures_root = (settings.data_directory / "fixtures").resolve()

    def search_documents(
        self, query: str, user: UserContext, endpoint: str = "/api/chat"
    ) -> list[dict[str, Any]]:
        """Keyword search over documents the caller is authorized to read."""
        words = set(re.findall(r"[a-z0-9]+", query.lower()))
        results: list[tuple[int, dict[str, Any]]] = []
        for document in self.store.documents():
            decision = self.authorization.can_read_document(user, document)
            if not decision.allowed:
                continue
            searchable = f"{document['title']} {document['content']}".lower()
            score = sum(word in searchable for word in words)
            if score or not words:
                results.append((score, document))
        results.sort(key=lambda item: (-item[0], item[1]["id"]))
        selected = [document for _, document in results[:5]]
        self.audit.record(
            user_email=user.email,
            endpoint=endpoint,
            tool_selected="search_documents",
            arguments={"query": query, "result_count": len(selected)},
            status="success",
            authorization_decision="filtered_by_policy",
            resource_type="document",
        )
        return selected

    def get_document(
        self,
        document_id: str,
        user: UserContext,
        endpoint: str = "/api/documents/{document_id}",
    ) -> dict[str, Any] | None:
        """Fetch one document after object-level authorization."""
        document = self.store.document(document_id)
        if not document:
            self.audit.record(
                user_email=user.email,
                endpoint=endpoint,
                tool_selected="get_document",
                arguments={"document_id": document_id},
                status="not_found",
                authorization_decision="n/a",
                resource_type="document",
                resource_id=document_id,
            )
            return None
        decision = self.authorization.can_read_document(user, document)
        if not decision.allowed:
            self.audit.record(
                user_email=user.email,
                endpoint=endpoint,
                tool_selected="get_document",
                arguments={"document_id": document_id},
                status="denied",
                authorization_decision=decision.reason,
                resource_type="document",
                resource_id=document_id,
            )
            return None
        self.audit.record(
            user_email=user.email,
            endpoint=endpoint,
            tool_selected="get_document",
            arguments={"document_id": document_id},
            status="success",
            authorization_decision=decision.reason,
            resource_type="document",
            resource_id=document_id,
        )
        return document

    def get_customer(
        self,
        customer_id: str,
        user: UserContext,
        endpoint: str = "/api/customers/{customer_id}",
    ) -> dict[str, Any] | None:
        """Fetch one customer; denied IDOR attempts emit cross_tenant_access_attempt."""
        customer = self.store.customer(customer_id)
        if not customer:
            self.audit.record(
                user_email=user.email,
                endpoint=endpoint,
                tool_selected="get_customer",
                arguments={"customer_id": customer_id},
                status="not_found",
                authorization_decision="n/a",
                resource_type="customer",
                resource_id=customer_id,
            )
            return None
        decision = self.authorization.can_read_customer(user, customer)
        if not decision.allowed:
            # Detection: API/tool customer IDOR attempt (additive to audit).
            self.audit.security_logger.emit(
                "cross_tenant_access_attempt",
                user_email=user.email,
                resource_id=customer_id,
                reason=decision.reason,
                endpoint=endpoint,
            )
            self.audit.record(
                user_email=user.email,
                endpoint=endpoint,
                tool_selected="get_customer",
                arguments={"customer_id": customer_id},
                status="denied",
                authorization_decision=decision.reason,
                resource_type="customer",
                resource_id=customer_id,
            )
            return None
        self.audit.record(
            user_email=user.email,
            endpoint=endpoint,
            tool_selected="get_customer",
            arguments={"customer_id": customer_id},
            status="success",
            authorization_decision=decision.reason,
            resource_type="customer",
            resource_id=customer_id,
        )
        return customer

    def queue_email(
        self,
        to: str,
        subject: str,
        body: str,
        user: UserContext,
        endpoint: str = "/api/tools/send-email",
    ) -> dict[str, Any]:
        """Persist a local outbox email after broker authorization/approval."""
        message_id = self.store.write_email(user.email, to, subject, body)
        self.audit.record(
            user_email=user.email,
            endpoint=endpoint,
            tool_selected="send_email",
            arguments={"to": to, "subject": subject, "body": body},
            status="success",
            authorization_decision="approved_execution",
            resource_type="email",
            approval_status="executed",
        )
        return {"message_id": message_id, "status": "queued locally"}

    def resolve_fixture_path(self, reference: str) -> Path:
        """Resolve a fixture ID or constrained local URL inside fixtures only."""

        fixture_id: str | None = None
        if reference.startswith("fixture://"):
            fixture_id = reference.removeprefix("fixture://").strip("/")
        else:
            parsed = urlsplit(reference)
            if parsed.scheme in {"http", "https"} and parsed.hostname in {
                "localhost",
                "127.0.0.1",
            }:
                relative = unquote(parsed.path).lstrip("/")
                # Map URL path basename or known IDs only.
                stem = Path(relative).name
                for known_id, filename in ALLOWED_FIXTURE_IDS.items():
                    if stem == filename or stem == known_id or relative == filename:
                        fixture_id = known_id
                        break
                if fixture_id is None and ".." not in relative:
                    # Reject unknown paths rather than mapping arbitrarily.
                    raise ValueError("Fixture is not allowlisted")
            else:
                raise ValueError("Resource must use fixture:// or local fixture address")

        if fixture_id not in ALLOWED_FIXTURE_IDS:
            raise ValueError("Fixture is not allowlisted")

        filename = ALLOWED_FIXTURE_IDS[fixture_id]
        candidate = (self.fixtures_root / filename).resolve()
        if self.fixtures_root not in candidate.parents and candidate != self.fixtures_root:
            raise ValueError("Fixture path escaped allowed root")
        if not str(candidate).startswith(str(self.fixtures_root)):
            raise ValueError("Fixture path escaped allowed root")
        if candidate.is_symlink():
            # Reject symlinks that could escape the fixtures root.
            real = candidate.resolve()
            if self.fixtures_root not in real.parents and real != self.fixtures_root:
                raise ValueError("Symlink escape rejected")
        if candidate.suffix.lower() not in ALLOWED_FIXTURE_EXTENSIONS:
            raise ValueError("Unexpected fixture file type")
        if not candidate.is_file():
            raise ValueError("Fixture not found")
        return candidate

    def fetch_internal_resource(
        self,
        url: str,
        user: UserContext,
        endpoint: str = "/api/chat",
    ) -> dict[str, str]:
        """Read an allowlisted local fixture; path escapes emit path_policy."""
        try:
            resource_path = self.resolve_fixture_path(url)
            content = resource_path.read_text(encoding="utf-8")
        except ValueError as exc:
            # Detection: first-class path_policy signal (audit_event still recorded).
            self.audit.security_logger.emit(
                "path_policy",
                user_email=user.email,
                reason=str(exc),
                url=url[:200],
                endpoint=endpoint,
            )
            self.audit.record(
                user_email=user.email,
                endpoint=endpoint,
                tool_selected="fetch_internal_resource",
                arguments={"url": url, "error": str(exc)},
                status="denied",
                authorization_decision="path_policy",
                resource_type="fixture",
            )
            raise
        self.audit.record(
            user_email=user.email,
            endpoint=endpoint,
            tool_selected="fetch_internal_resource",
            arguments={"url": url, "fixture": resource_path.name},
            status="success",
            authorization_decision="allowlisted_fixture",
            resource_type="fixture",
            resource_id=resource_path.name,
        )
        return {"url": url, "content": content}
