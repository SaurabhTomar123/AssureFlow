"""Process manager (spec section 2): CaseWorkflow.next(case_state, event) -> [commands].

A pure function. Handlers and room-command parsers only execute the returned commands; they never
choose the next step themselves (G-18).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from domain import states as st


@dataclass(frozen=True)
class Event:
    name: str
    blocking: bool = False
    ca_attention: bool = False
    all_blocking_resolved: bool = False


@dataclass(frozen=True)
class Command:
    name: str
    args: dict[str, str] = field(default_factory=dict)


def C(name: str, **args: str) -> Command:
    return Command(name, dict(args))


class CaseWorkflow:
    @staticmethod
    def next(case_state: str | None, event: Event) -> list[Command]:
        e = event.name
        if e == "document_preserved" and case_state == st.RECEIVED:
            return [C("enqueue_extraction"), C("notify_owner", template="preserved")]
        if e == "replacement_preserved":
            st.target(case_state or "", "replacement_accepted")
            return [
                C("transition", command="replacement_accepted"),
                C("supersede_current_revision", reason="document_replaced"),
                C("enqueue_extraction"),
                C("notify_owner", template="replacement_received"),
            ]
        if e == "extraction_leased":
            if case_state == st.RECEIVED:
                return [C("transition", command="extraction_leased")]
            return []
        if e == "extraction_persisted":
            st.target(case_state or "", "extraction_persisted")
            return [C("transition", command="extraction_persisted"), C("notify_owner", template="summary")]
        if e == "extraction_exhausted":
            st.target(case_state or "", "extraction_exhausted")
            return [
                C("transition", command="extraction_exhausted"),
                C("notify_owner", template="extraction_failed"),
            ]
        if e == "typed_correction":
            st.target(case_state or "", "typed_correction")
            cmds = [C("supersede_open_issues", reason="revision_replaced")]
            if case_state == st.APPROVED:
                cmds.append(C("invalidate_decisions", reason="revision_replaced"))
            return [C("transition", command="typed_correction"), *cmds, C("notify_owner", template="summary")]
        if e == "owner_confirmed":
            st.target(case_state or "", "confirm")
            return [
                C("transition", command="confirm"),
                C("claim_duplicate_key"),
                C("assign_period"),
                C("enqueue_checks"),
                C("notify_owner", template="confirmed"),
            ]
        if e == "checks_completed":
            command = "checks_blocking" if event.blocking else "checks_clean"
            st.target(case_state or "", command)
            cmds = [C("transition", command=command), C("route_issues")]
            if event.ca_attention or not event.blocking:
                cmds.append(C("open_review_request"))
            return cmds
        if e == "issue_resolved":
            if event.all_blocking_resolved and case_state == st.NEEDS_RESOLUTION:
                return [C("transition", command="issues_resolved"), C("open_review_request")]
            return []
        return []
