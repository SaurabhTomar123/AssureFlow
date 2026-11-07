"""Unified error contract (spec section 6). Chat messages are built from the code, never raw exceptions."""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    status = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def envelope(self, correlation_id: str) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
                "correlation_id": correlation_id,
            }
        }


class Unauthenticated(DomainError):
    status, code = 401, "UNAUTHENTICATED"


class Forbidden(DomainError):
    status, code = 403, "FORBIDDEN"


class NotFound(DomainError):
    status, code = 404, "NOT_FOUND"


class StaleRevision(DomainError):
    status, code = 409, "STALE_REVISION"


class IdempotencyConflict(DomainError):
    status, code = 409, "IDEMPOTENCY_CONFLICT"


class InvalidTransition(DomainError):
    status, code = 409, "INVALID_TRANSITION"


class SnapshotStale(DomainError):
    status, code = 409, "SNAPSHOT_STALE"


class LeaseLost(DomainError):
    status, code = 409, "LEASE_LOST"


class ValidationFailed(DomainError):
    status, code = 422, "VALIDATION_ERROR"


class UnsupportedMedia(DomainError):
    status, code = 422, "UNSUPPORTED_MEDIA"


class LimitExceeded(DomainError):
    status, code = 422, "LIMIT_EXCEEDED"


class NotAvailable(DomainError):
    """A feature deferred by the hackathon cut (spec section 10)."""

    status, code = 422, "NOT_AVAILABLE_IN_THIS_RELEASE"


class MatchStale(DomainError):
    """U2: the purchase inputs changed after the match, review or authorization being acted on."""

    status, code = 409, "MATCH_STALE"


class OrderAlreadyLinked(DomainError):
    status, code = 409, "ORDER_ALREADY_LINKED"
