import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlsplit

from .models import UserContext
from .store import Store


class OrionTools:
    def __init__(self, store: Store, data_directory: Path):
        self.store = store
        self.data_directory = data_directory

    @staticmethod
    def _can_read_document(document: dict[str, Any], user: UserContext) -> bool:
        if document["classification"] == "public":
            return True
        if document["classification"] == "project":
            return document["project"] in user.projects or user.role in {
                "manager",
                "administrator",
            }
        return user.role in {"manager", "administrator"}

    def _invoke(
        self,
        name: str,
        endpoint: str,
        arguments: dict[str, Any],
        user: UserContext,
        operation: Callable[[], Any],
    ) -> Any:
        try:
            result = operation()
        except Exception:
            self.store.write_audit(
                user.email, endpoint, name, arguments, "failure"
            )
            raise
        self.store.write_audit(user.email, endpoint, name, arguments, "success")
        return result

    def search_documents(
        self, query: str, user: UserContext, endpoint: str = "/api/chat"
    ) -> list[dict[str, Any]]:
        def search() -> list[dict[str, Any]]:
            words = set(re.findall(r"[a-z0-9]+", query.lower()))
            results = []
            for document in self.store.documents():
                if not self._can_read_document(document, user):
                    continue
                searchable = (
                    f"{document['title']} {document['content']}".lower()
                )
                score = sum(word in searchable for word in words)
                if score or not words:
                    results.append((score, document))
            results.sort(key=lambda item: (-item[0], item[1]["id"]))
            return [document for _, document in results[:5]]

        return self._invoke(
            "search_documents",
            endpoint,
            {"query": query},
            user,
            search,
        )

    def get_document(
        self,
        document_id: str,
        user: UserContext,
        endpoint: str = "/api/documents/{document_id}",
    ) -> dict[str, Any] | None:
        def get() -> dict[str, Any] | None:
            document = self.store.document(document_id)
            if document and not self._can_read_document(document, user):
                return None
            return document

        return self._invoke(
            "get_document",
            endpoint,
            {"document_id": document_id},
            user,
            get,
        )

    def get_customer(
        self,
        customer_id: str,
        user: UserContext,
        endpoint: str = "/api/customers/{customer_id}",
    ) -> dict[str, Any] | None:
        return self._invoke(
            "get_customer",
            endpoint,
            {"customer_id": customer_id},
            user,
            lambda: self.store.customer(customer_id),
        )

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        user: UserContext,
        endpoint: str = "/api/tools/send-email",
    ) -> dict[str, Any]:
        arguments = {"to": to, "subject": subject, "body": body}

        def send() -> dict[str, Any]:
            message_id = self.store.write_email(user.email, to, subject, body)
            return {"message_id": message_id, "status": "queued locally"}

        return self._invoke(
            "send_email", endpoint, arguments, user, send
        )

    def fetch_internal_resource(
        self,
        url: str,
        user: UserContext,
        endpoint: str = "/api/chat",
    ) -> dict[str, str]:
        def fetch() -> dict[str, str]:
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
                "localhost",
                "127.0.0.1",
            }:
                raise ValueError("Resource must use a local fixture address")

            relative_path = unquote(parsed.path).lstrip("/")
            resource_path = (
                self.data_directory / "fixtures" / relative_path
            ).resolve()
            allowed_root = self.data_directory.resolve()
            if resource_path != allowed_root and allowed_root not in resource_path.parents:
                raise ValueError("Resource is not available")
            return {
                "url": url,
                "content": resource_path.read_text(encoding="utf-8"),
            }

        return self._invoke(
            "fetch_internal_resource",
            endpoint,
            {"url": url},
            user,
            fetch,
        )
