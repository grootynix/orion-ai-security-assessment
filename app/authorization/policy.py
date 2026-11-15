"""Deny-by-default authorization used by API, tools, and retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models import UserContext

ROLE_ORDER = {"employee": 0, "manager": 1, "administrator": 2}


@dataclass(frozen=True)
class AuthorizationDecision:
    """Immutable allow/deny result with a machine-readable reason code."""

    allowed: bool
    reason: str
    action: str
    resource_type: str
    resource_id: str | None = None


class AuthorizationService:
    """
    Central deny-by-default policy engine.

    Trust assumptions: UserContext must already be rebound from the identity
    directory. Never trust client-supplied roles or project claims.
    """

    def decide(
        self,
        *,
        allowed: bool,
        reason: str,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
    ) -> AuthorizationDecision:
        """Build a structured decision for callers and audit/detection."""
        return AuthorizationDecision(
            allowed=allowed,
            reason=reason,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
        )

    def has_minimum_role(self, user: UserContext, minimum: str) -> bool:
        """True when the user's rebound role meets or exceeds `minimum`."""
        return ROLE_ORDER.get(user.role, -1) >= ROLE_ORDER.get(minimum, 999)

    def can_read_document(
        self, user: UserContext, document: dict[str, Any]
    ) -> AuthorizationDecision:
        """Object-level document ACL by classification and project membership."""
        classification = document.get("classification")
        project = document.get("project")
        document_id = str(document.get("id", ""))
        if classification == "public":
            return self.decide(
                allowed=True,
                reason="public_document",
                action="read_document",
                resource_type="document",
                resource_id=document_id,
            )
        if classification == "project":
            if project in user.projects or self.has_minimum_role(user, "manager"):
                return self.decide(
                    allowed=True,
                    reason="project_membership_or_manager",
                    action="read_document",
                    resource_type="document",
                    resource_id=document_id,
                )
            return self.decide(
                allowed=False,
                reason="project_access_denied",
                action="read_document",
                resource_type="document",
                resource_id=document_id,
            )
        if self.has_minimum_role(user, "manager"):
            return self.decide(
                allowed=True,
                reason="management_document",
                action="read_document",
                resource_type="document",
                resource_id=document_id,
            )
        return self.decide(
            allowed=False,
            reason="insufficient_role",
            action="read_document",
            resource_type="document",
            resource_id=document_id,
        )

    def can_read_customer(
        self, user: UserContext, customer: dict[str, Any]
    ) -> AuthorizationDecision:
        """Customer IDOR control: assignee or manager+ only."""
        customer_id = str(customer.get("id", ""))
        assigned_to = str(customer.get("assigned_to", "")).lower()
        if user.email.lower() == assigned_to:
            return self.decide(
                allowed=True,
                reason="assignee",
                action="read_customer",
                resource_type="customer",
                resource_id=customer_id,
            )
        if self.has_minimum_role(user, "manager"):
            return self.decide(
                allowed=True,
                reason="manager_override",
                action="read_customer",
                resource_type="customer",
                resource_id=customer_id,
            )
        return self.decide(
            allowed=False,
            reason="customer_access_denied",
            action="read_customer",
            resource_type="customer",
            resource_id=customer_id,
        )

    def can_send_email(self, user: UserContext) -> AuthorizationDecision:
        """Email send requires manager+; recipient allowlist is enforced elsewhere."""
        if self.has_minimum_role(user, "manager"):
            return self.decide(
                allowed=True,
                reason="manager_or_admin",
                action="send_email",
                resource_type="email",
            )
        return self.decide(
            allowed=False,
            reason="insufficient_role",
            action="send_email",
            resource_type="email",
        )

    def can_read_audit(self, user: UserContext) -> AuthorizationDecision:
        """Audit log read is administrator-only."""
        if self.has_minimum_role(user, "administrator"):
            return self.decide(
                allowed=True,
                reason="administrator",
                action="read_audit",
                resource_type="audit",
            )
        return self.decide(
            allowed=False,
            reason="insufficient_role",
            action="read_audit",
            resource_type="audit",
        )

    def can_read_outbox(self, user: UserContext) -> AuthorizationDecision:
        """Local email outbox read is administrator-only."""
        if self.has_minimum_role(user, "administrator"):
            return self.decide(
                allowed=True,
                reason="administrator",
                action="read_outbox",
                resource_type="outbox",
            )
        return self.decide(
            allowed=False,
            reason="insufficient_role",
            action="read_outbox",
            resource_type="outbox",
        )

    def can_approve_action(
        self, user: UserContext, requested_by: str
    ) -> AuthorizationDecision:
        """Consequential tool approvals require manager+."""
        if self.has_minimum_role(user, "manager"):
            return self.decide(
                allowed=True,
                reason="manager_or_admin",
                action="approve_action",
                resource_type="pending_action",
                resource_id=requested_by,
            )
        return self.decide(
            allowed=False,
            reason="insufficient_role",
            action="approve_action",
            resource_type="pending_action",
        )

    def require_role(self, user: UserContext, minimum: str) -> AuthorizationDecision:
        """Generic minimum-role gate used by thin API surfaces."""
        if self.has_minimum_role(user, minimum):
            return self.decide(
                allowed=True,
                reason="role_satisfied",
                action="require_role",
                resource_type="role",
                resource_id=minimum,
            )
        return self.decide(
            allowed=False,
            reason="insufficient_role",
            action="require_role",
            resource_type="role",
            resource_id=minimum,
        )
