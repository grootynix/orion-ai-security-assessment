"""Retrieval-time authorization wrapper around the document index."""

from __future__ import annotations

from typing import Any

from app.models import UserContext
from app.tools.implementations import ToolImplementations

RETRIEVAL_CONFIG_VERSION = "keyword-v1"
EMBEDDING_MODEL_VERSION = "none-local-keyword"


class RetrievalService:
    """Tenant-aware document retrieval with provenance metadata."""

    def __init__(self, tools: ToolImplementations):
        self.tools = tools

    def search(self, query: str, user: UserContext) -> dict[str, Any]:
        """Retrieve authorized documents with config/version provenance."""
        documents = self.tools.search_documents(query, user, endpoint="/retrieval")
        return {
            "documents": documents,
            "retrieval_config_version": RETRIEVAL_CONFIG_VERSION,
            "embedding_model_version": EMBEDDING_MODEL_VERSION,
            "authorized": True,
        }
