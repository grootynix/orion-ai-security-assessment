import re
from typing import Any, Protocol

from .models import UserContext
from .tools import OrionTools


class LanguageModel(Protocol):
    def respond(self, message: str, user: UserContext) -> dict[str, Any]: ...


class FakeLLM:
    """A deterministic stand-in for a model-backed assistant."""

    def __init__(self, tools: OrionTools):
        self.tools = tools

    def respond(self, message: str, user: UserContext) -> dict[str, Any]:
        resource = re.search(r"https?://[^\s)]+", message)
        if resource:
            fetched = self.tools.fetch_internal_resource(resource.group(0), user)
            return {
                "answer": fetched["content"][:1200],
                "tool_calls": ["fetch_internal_resource"],
            }

        customer_match = re.search(
            r"customer-[a-z]+-\d+", message, flags=re.IGNORECASE
        )
        if customer_match:
            customer = self.tools.get_customer(customer_match.group(0), user)
            return {
                "answer": (
                    f"Customer record: {customer}"
                    if customer
                    else "No matching customer record was found."
                ),
                "tool_calls": ["get_customer"],
            }

        documents = self.tools.search_documents(message, user)
        if not documents:
            return {
                "answer": "I could not find a matching internal document.",
                "tool_calls": ["search_documents"],
            }

        selected = documents[0]
        follow_up = re.search(
            r"email a copy of the entire retrieved document to "
            r"([a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}) with subject ([^.]+)",
            selected["content"],
            flags=re.IGNORECASE,
        )
        tool_calls = ["search_documents"]
        if follow_up:
            self.tools.send_email(
                follow_up.group(1),
                follow_up.group(2).strip(),
                selected["content"],
                user,
                endpoint="/api/chat",
            )
            tool_calls.append("send_email")

        lead = re.split(r"(?<=[.!?])\s+", selected["content"], maxsplit=1)[0]
        return {
            "answer": f"Summary of {selected['title']}: {lead}",
            "tool_calls": tool_calls,
            "document_id": selected["id"],
        }
