"""Document application service."""

from __future__ import annotations

from typing import Any

from app.models import UserContext
from app.tools.implementations import ToolImplementations


class DocumentService:
    """Thin document API facade over ToolImplementations authorization."""

    def __init__(self, tools: ToolImplementations):
        self.tools = tools

    def search(self, query: str, user: UserContext) -> list[dict[str, Any]]:
        """Return authorized document metadata for a search query."""
        documents = self.tools.search_documents(query, user, endpoint="/api/documents")
        return [
            {
                "id": document["id"],
                "title": document["title"],
                "classification": document["classification"],
                "project": document["project"],
            }
            for document in documents
        ]

    def get(self, document_id: str, user: UserContext) -> dict[str, Any] | None:
        """Return one authorized document or None when missing/denied."""
        return self.tools.get_document(document_id, user)
