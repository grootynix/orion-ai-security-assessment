"""Shared API and domain models."""

from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["employee", "manager", "administrator"]


class UserContext(BaseModel):
    """Canonical authenticated identity after server-side rebinding."""

    email: str
    role: Role
    projects: list[str] = Field(default_factory=list)
    tenant_id: str = "orion-local"


class TokenRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class SendEmailRequest(BaseModel):
    to: str = Field(min_length=3, max_length=254)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approve", "deny"]


class PendingActionView(BaseModel):
    action_id: str
    tool_name: str
    arguments: dict[str, Any]
    status: str
    requested_by: str
