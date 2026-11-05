"""Allowed case transitions (spec section 4). Any other (from, command) pair is INVALID_TRANSITION.

Revision, issue, job and snapshot statuses are separate machines and never share this column.
"""

from __future__ import annotations

from typing import Protocol

from common.errors import InvalidTransition

RECEIVED = "received"
PROCESSING = "processing"
EXTRACTION_FAILED = "extraction_failed"
NEEDS_CONFIRMATION = "needs_confirmation"
CHECKING = "checking"
NEEDS_RESOLUTION = "needs_resolution"
READY_FOR_CA = "ready_for_ca"
APPROVED = "approved"
EXCLUDED = "excluded"

ALL_STATES = (
    RECEIVED,
    PROCESSING,
    EXTRACTION_FAILED,
    NEEDS_CONFIRMATION,
    CHECKING,
    NEEDS_RESOLUTION,
    READY_FOR_CA,
    APPROVED,
    EXCLUDED,
)

TRANSITIONS: dict[tuple[str, str], str] = {
    (RECEIVED, "extraction_leased"): PROCESSING,
    (PROCESSING, "extraction_persisted"): NEEDS_CONFIRMATION,
    (PROCESSING, "extraction_exhausted"): EXTRACTION_FAILED,
    (RECEIVED, "extraction_exhausted"): EXTRACTION_FAILED,
    (EXTRACTION_FAILED, "retry_extraction"): PROCESSING,
    (NEEDS_CONFIRMATION, "typed_correction"): NEEDS_CONFIRMATION,
    (NEEDS_RESOLUTION, "typed_correction"): NEEDS_CONFIRMATION,
    (READY_FOR_CA, "typed_correction"): NEEDS_CONFIRMATION,
    (APPROVED, "typed_correction"): NEEDS_CONFIRMATION,
    (NEEDS_CONFIRMATION, "confirm"): CHECKING,
    (CHECKING, "checks_clean"): READY_FOR_CA,
    (CHECKING, "checks_blocking"): NEEDS_RESOLUTION,
    (NEEDS_RESOLUTION, "issues_resolved"): READY_FOR_CA,
    (READY_FOR_CA, "ca_include"): APPROVED,
    (NEEDS_RESOLUTION, "ca_include_with_override"): APPROVED,
    (NEEDS_CONFIRMATION, "ca_exclude"): EXCLUDED,
    (NEEDS_RESOLUTION, "ca_exclude"): EXCLUDED,
    (READY_FOR_CA, "ca_exclude"): EXCLUDED,
    (EXTRACTION_FAILED, "ca_exclude"): EXCLUDED,
    (APPROVED, "ca_exclude"): EXCLUDED,
    (NEEDS_RESOLUTION, "ca_resolve_issue"): NEEDS_RESOLUTION,
    (NEEDS_RESOLUTION, "ca_request_owner_clarification"): NEEDS_RESOLUTION,
    (READY_FOR_CA, "ca_request_owner_clarification"): NEEDS_RESOLUTION,
    (NEEDS_RESOLUTION, "ca_request_supplier_replacement"): NEEDS_RESOLUTION,
    (READY_FOR_CA, "ca_request_supplier_replacement"): NEEDS_RESOLUTION,
    (EXCLUDED, "ca_reopen"): NEEDS_RESOLUTION,
}

# A replacement document is accepted from any state except excluded.
for _state in ALL_STATES:
    if _state != EXCLUDED:
        TRANSITIONS[(_state, "replacement_accepted")] = PROCESSING


class HasStatus(Protocol):
    status: str


def target(current: str, command: str) -> str:
    try:
        return TRANSITIONS[(current, command)]
    except KeyError as exc:
        raise InvalidTransition(
            f"'{command}' is not allowed while the case is {current}",
            {"from": current, "command": command},
        ) from exc


def transition(case: HasStatus, command: str) -> tuple[str, str]:
    """The only place a case status changes (G-08)."""
    old = case.status
    new = target(old, command)
    case.status = new
    return old, new
