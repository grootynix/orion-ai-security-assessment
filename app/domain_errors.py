"""Typed domain errors mapped to safe HTTP responses."""

from __future__ import annotations


class OrionDomainError(Exception):
    """Base domain error. Never include secrets in messages."""

    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class AuthError(OrionDomainError):
    status_code = 401


class AuthzDenied(OrionDomainError):
    status_code = 403


class ToolPolicyError(OrionDomainError):
    status_code = 403


class NotFoundError(OrionDomainError):
    status_code = 404


class RateLimitError(OrionDomainError):
    status_code = 429
