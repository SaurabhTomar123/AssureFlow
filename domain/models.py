"""Physical schema contract (spec section 6). Table names are binding.

Every table carries `info={"phase": "Pn"}`; each Alembic revision creates exactly its phase's tables
(capability matrix, section 9). Settled money is NUMERIC(14,2); quantity and unit price NUMERIC(18,4);
rates NUMERIC(7,4); all timestamps are timestamptz (UTC).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from common.db import Base
from common.ids import new_id

MONEY = Numeric(14, 2)
QTY = Numeric(18, 4)
RATE = Numeric(7, 4)


def utcnow() -> datetime:
    return datetime.now(UTC)


def pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=new_id)


def ts(nullable: bool = False) -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=nullable, default=None if nullable else utcnow)


def shop_fk() -> tuple[ForeignKeyConstraint]:
    return (ForeignKeyConstraint(["practice_id", "shop_id"], ["shops.practice_id", "shops.id"]),)


# --------------------------------------------------------------------------------------------- P0


class EnvironmentRow(Base):
    __tablename__ = "environment"
    __table_args__ = ({"info": {"phase": "P0"}},)
    name: Mapped[str] = mapped_column(String(16), primary_key=True)
    created_at: Mapped[datetime] = ts()


class RefCounter(Base):
    __tablename__ = "ref_counters"
    __table_args__ = ({"info": {"phase": "P0"}},)
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("practices.id"), primary_key=True)
    prefix: Mapped[str] = mapped_column(String(8), primary_key=True)
    next_value: Mapped[int] = mapped_column(BigInteger)


class Practice(Base):
    __tablename__ = "practices"
    __table_args__ = ({"info": {"phase": "P0"}},)
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = ts()


class Shop(Base):
    __tablename__ = "shops"
    __table_args__ = (
        UniqueConstraint("practice_id", "gstin"),
        UniqueConstraint("practice_id", "id"),
        UniqueConstraint("practice_id", "code"),
        {"info": {"phase": "P0"}},
    )
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("practices.id"))
    code: Mapped[str] = mapped_column(String(40))
    gstin: Mapped[str] = mapped_column(String(15))
    state_code: Mapped[str] = mapped_column(String(2))
    name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    purchase_assurance: Mapped[bool] = mapped_column(Boolean, default=False)  # U2 opt-in
    shared_review: Mapped[bool] = mapped_column(Boolean, default=False)  # D-31: review in the shop group
    created_at: Mapped[datetime] = ts()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('owner','ca','practice_staff','operator','developer','staff','client')", name="users_role_check"
        ),
        UniqueConstraint("practice_id", "handle"),
        {"info": {"phase": "P0"}},
    )
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("practices.id"))
    handle: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = ts()


class ChatIdentity(Base):
    __tablename__ = "chat_identities"
    __table_args__ = (UniqueConstraint("platform", "platform_user_id"), {"info": {"phase": "P0"}})
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("practices.id"))
    platform: Mapped[str] = mapped_column(String(32))
    platform_user_id: Mapped[str] = mapped_column(String(255))
    chat_username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    verified_at: Mapped[datetime] = ts()
    revoked_at: Mapped[datetime | None] = ts(nullable=True)


class RoomBinding(Base):
    __tablename__ = "room_bindings"
    __table_args__ = (
        UniqueConstraint("environment", "switch_room_id"),
        CheckConstraint(
            "purpose IN ('practice_home','shop_intake','ca_review','operations','synthetic_testing','delivery','submission')",
            name="room_bindings_purpose_check",
        ),
        {"info": {"phase": "P0"}},
    )
    id: Mapped[uuid.UUID] = pk()
    environment: Mapped[str] = mapped_column(String(16))
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("practices.id"))
    name: Mapped[str] = mapped_column(String(120))
    switch_room_id: Mapped[str] = mapped_column(String(255))
    messaging_destination: Mapped[str | None] = mapped_column(String(255), nullable=True)
    purpose: Mapped[str] = mapped_column(String(24))
    human_roles: Mapped[list[str]] = mapped_column(JSONB, default=list)
    permitted_agent_senders: Mapped[list[str]] = mapped_column(JSONB, default=list)
    agent_roles_and_tools: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    config_version: Mapped[str] = mapped_column(String(32))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = ts()


class RoomBindingShop(Base):
    __tablename__ = "room_binding_shops"
    __table_args__ = ({"info": {"phase": "P0"}},)
    room_binding_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("room_bindings.id"), primary_key=True)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("shops.id"), primary_key=True)


class RoomMember(Base):
    """Declared human audience of a room; the outbox rechecks it before every delivery (G-06)."""

    __tablename__ = "room_members"
    __table_args__ = ({"info": {"phase": "P0"}},)
    room_binding_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("room_bindings.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), primary_key=True)
    removed_at: Mapped[datetime | None] = ts(nullable=True)


class ShopMembership(Base):
    __tablename__ = "shop_memberships"
    __table_args__ = ({"info": {"phase": "P0"}},)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), primary_key=True)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("shops.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), default="owner")
    revoked_at: Mapped[datetime | None] = ts(nullable=True)


class CaAssignment(Base):
    __tablename__ = "ca_assignments"
    __table_args__ = ({"info": {"phase": "P0"}},)
    id: Mapped[uuid.UUID] = pk()
    ca_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("shops.id"))
    effective_from: Mapped[datetime] = ts()
    effective_to: Mapped[datetime | None] = ts(nullable=True)


class AdapterState(Base):
    __tablename__ = "adapter_state"
    __table_args__ = ({"info": {"phase": "P0"}},)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    connection_id: Mapped[str] = mapped_column(String(64))
    generation: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cursor: Mapped[int] = mapped_column(BigInteger, default=0)
    updated_at: Mapped[datetime] = ts()


class InboxEvent(Base):
    __tablename__ = "inbox_events"
    __table_args__ = (
        UniqueConstraint("bridge_id", "event_id"),
        CheckConstraint("outcome IN ('pending','processed','ignored','rejected','failed')"),
        {"info": {"phase": "P0"}},
    )
    id: Mapped[uuid.UUID] = pk()
    bridge_id: Mapped[str] = mapped_column(String(255))
    event_id: Mapped[str] = mapped_column(String(255))
    switch_room_id: Mapped[str] = mapped_column(String(255))
    room_binding_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("room_bindings.id"), nullable=True
    )
    sender_ref: Mapped[str] = mapped_column(String(255))
    addressed_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kind: Mapped[str] = mapped_column(String(32))
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, default="")
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    payload_hash: Mapped[str] = mapped_column(String(64))
    sequence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), default="pending")
    outcome_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = ts()
    processed_at: Mapped[datetime | None] = ts(nullable=True)


class RequestContext(Base):
    __tablename__ = "request_contexts"
    __table_args__ = ({"info": {"phase": "P0"}},)
    context_id: Mapped[uuid.UUID] = pk()
    environment: Mapped[str] = mapped_column(String(16))
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("practices.id"))
    shop_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("shops.id"), nullable=True)
    room_binding_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("room_bindings.id"))
    source_event_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("inbox_events.id"))
    verified_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    addressed_agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = ts()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExecutionGrant(Base):
    __tablename__ = "execution_grants"
    __table_args__ = (
        *shop_fk(),
        CheckConstraint(
            "operation IN ('preserve_document','extract_generation','run_checks','notify',"
            "'build_snapshot','build_export','import_statement','reconcile','run_acceptance',"
            "'run_purchase_match','build_purchase_export')",
            name="execution_grants_operation_check",
        ),
        {"info": {"phase": "P0"}},
    )
    grant_id: Mapped[uuid.UUID] = pk()
    environment: Mapped[str] = mapped_column(String(16))
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    operation: Mapped[str] = mapped_column(String(24))
    target_case_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    target_generation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    target_receipt_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    initiating_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    initiating_context_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    initiating_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    issued_at: Mapped[datetime] = ts()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = ts(nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Receipt(Base):
    __tablename__ = "receipts"
    __table_args__ = (
        *shop_fk(),
        CheckConstraint("status IN ('accepted','preserved','rejected_file','duplicate')"),
        {"info": {"phase": "P0"}},
    )
    id: Mapped[uuid.UUID] = pk()
    public_ref: Mapped[str] = mapped_column(String(16))
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    inbox_event_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("inbox_events.id"))
    attachment_index: Mapped[int] = mapped_column(Integer, default=0)
    filename: Mapped[str] = mapped_column(String(255))
    declared_mime: Mapped[str | None] = mapped_column(String(100), nullable=True)
    media_ref: Mapped[str] = mapped_column(String(512))
    replaces_invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="accepted")
    reject_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = ts()


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        *shop_fk(),
        Index("ix_documents_shop_sha", "shop_id", "sha256"),
        {"info": {"phase": "P0"}},
    )
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    receipt_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("receipts.id"))
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    document_generation: Mapped[int] = mapped_column(Integer, default=1)
    sha256: Mapped[str] = mapped_column(String(64))
    mime: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    page_count: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(512))
    page_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = ts()


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("dedupe_key"),
        CheckConstraint("lane IN ('fast','io','slow')"),
        CheckConstraint("status IN ('queued','leased','succeeded','failed','cancelled','dead')"),
        Index("ix_jobs_lane_status", "lane", "status", "run_after"),
        {"info": {"phase": "P0"}},
    )
    id: Mapped[uuid.UUID] = pk()
    type: Mapped[str] = mapped_column(String(40))
    lane: Mapped[str] = mapped_column(String(8))
    grant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("execution_grants.grant_id"), nullable=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    dedupe_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(12), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_generation: Mapped[int] = mapped_column(BigInteger, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = ts(nullable=True)
    run_after: Mapped[datetime] = ts()
    started_at: Mapped[datetime | None] = ts(nullable=True)
    finished_at: Mapped[datetime | None] = ts(nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = ts()


class Outbox(Base):
    __tablename__ = "outbox"
    __table_args__ = (
        UniqueConstraint("action_id", "destination"),
        UniqueConstraint("destination", "seq"),
        CheckConstraint("status IN ('pending','delivered','withheld','dead')"),
        {"info": {"phase": "P0"}},
    )
    id: Mapped[uuid.UUID] = pk()
    action_id: Mapped[str] = mapped_column(String(128))
    destination: Mapped[str] = mapped_column(String(255))
    room_binding_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("room_bindings.id"))
    seq: Mapped[int] = mapped_column(BigInteger)
    supersedes_action_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    case_ref: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="text")
    body: Mapped[str] = mapped_column(Text)
    attachments: Mapped[list[str]] = mapped_column(JSONB, default=list)
    audience_check: Mapped[str] = mapped_column(String(10), default="required")
    status: Mapped[str] = mapped_column(String(10), default="pending")
    transport_attempts: Mapped[int] = mapped_column(Integer, default=0)
    delivered_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = ts()
    delivered_at: Mapped[datetime | None] = ts(nullable=True)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = ({"info": {"phase": "P0"}},)
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    actor_scope: Mapped[str] = mapped_column(String(255), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status_code: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = ts()


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = ({"info": {"phase": "P0"}},)
    id: Mapped[uuid.UUID] = pk()
    environment: Mapped[str] = mapped_column(String(16))
    practice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    shop_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    actor: Mapped[str] = mapped_column(String(255))
    request_context_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    grant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    outcome: Mapped[str] = mapped_column(String(16))
    request_id: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = ts()


# --------------------------------------------------------------------------------------------- P1


class Invoice(Base):
    """A stable case: exists from document preservation onward."""

    __tablename__ = "invoices"
    __table_args__ = (
        *shop_fk(),
        UniqueConstraint("practice_id", "case_ref"),
        CheckConstraint(
            "status IN ('received','processing','extraction_failed','needs_confirmation','checking',"
            "'needs_resolution','ready_for_ca','approved','excluded')"
        ),
        {"info": {"phase": "P1"}},
    )
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    case_ref: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24))
    document_generation: Mapped[int] = mapped_column(Integer, default=1)
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    split_from_invoice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    period: Mapped[str | None] = mapped_column(String(7), nullable=True)
    period_basis: Mapped[str | None] = mapped_column(String(20), nullable=True)
    event_seq: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = ts()
    updated_at: Mapped[datetime] = ts()


class InvoiceRevision(Base):
    __tablename__ = "invoice_revisions"
    __table_args__ = (
        *shop_fk(),
        UniqueConstraint("invoice_id", "revision_no"),
        CheckConstraint("status IN ('draft','confirmed','superseded')"),
        CheckConstraint("source IN ('extraction','replacement','human')"),
        {"info": {"phase": "P1"}},
    )
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("invoices.id"))
    revision_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="draft")
    parent_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("documents.id"))
    document_generation: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(12))
    document_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supplier_gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    recipient_gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    invoice_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    place_of_supply: Mapped[str | None] = mapped_column(String(2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    tax_printed_per_line: Mapped[bool] = mapped_column(Boolean, default=True)
    taxable_total: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    cgst_total: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    sgst_total: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    igst_total: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    cess_total: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    round_off: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    invoice_total: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    multiple_invoices: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    confirmed_at: Mapped[datetime | None] = ts(nullable=True)
    superseded_at: Mapped[datetime | None] = ts(nullable=True)
    created_at: Mapped[datetime] = ts()


class LineItem(Base):
    __tablename__ = "line_items"
    __table_args__ = (*shop_fk(), UniqueConstraint("revision_id", "line_no"), {"info": {"phase": "P1"}})
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("invoice_revisions.id"))
    line_no: Mapped[int] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hsn_sac: Mapped[str | None] = mapped_column(String(16), nullable=True)
    qty: Mapped[Decimal | None] = mapped_column(QTY, nullable=True)
    unit_price: Mapped[Decimal | None] = mapped_column(QTY, nullable=True)
    discount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    taxable_value: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    cgst_rate: Mapped[Decimal | None] = mapped_column(RATE, nullable=True)
    sgst_rate: Mapped[Decimal | None] = mapped_column(RATE, nullable=True)
    igst_rate: Mapped[Decimal | None] = mapped_column(RATE, nullable=True)
    combined_rate: Mapped[Decimal | None] = mapped_column(RATE, nullable=True)
    cgst_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    sgst_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    igst_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)


class FieldEvidence(Base):
    __tablename__ = "field_evidence"
    __table_args__ = (*shop_fk(), {"info": {"phase": "P1"}})
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("invoice_revisions.id"))
    field_path: Mapped[str] = mapped_column(String(64))
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    source: Mapped[str] = mapped_column(String(8))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = ts()


class CaseEvent(Base):
    __tablename__ = "case_events"
    __table_args__ = (*shop_fk(), UniqueConstraint("case_id", "seq"), {"info": {"phase": "P1"}})
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("invoices.id"))
    seq: Mapped[int] = mapped_column(BigInteger)
    type: Mapped[str] = mapped_column(String(48))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    request_context_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    grant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = ts()


class DuplicateLink(Base):
    __tablename__ = "duplicate_links"
    __table_args__ = (*shop_fk(), {"info": {"phase": "P1"}})
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(16))
    invoice_a: Mapped[uuid.UUID] = mapped_column(Uuid)
    receipt_b: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    invoice_b: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = ts()


class UsageRecord(Base):
    __tablename__ = "usage_records"
    __table_args__ = ({"info": {"phase": "P1"}},)
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    shop_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    stage: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    est_cost_inr: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[str] = mapped_column(String(40), default="ok")
    at: Mapped[datetime] = ts()


# --------------------------------------------------------------------------------------------- P2


class RuleDefinition(Base):
    __tablename__ = "rule_definitions"
    __table_args__ = ({"info": {"phase": "P2"}},)
    rule_id: Mapped[str] = mapped_column(String(24), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile: Mapped[str] = mapped_column(String(48))
    effective_from: Mapped[str] = mapped_column(String(10))
    effective_to: Mapped[str | None] = mapped_column(String(10), nullable=True)
    category: Mapped[str] = mapped_column(String(24))
    overridable: Mapped[bool] = mapped_column(Boolean)
    reference: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(255))


class CheckRun(Base):
    __tablename__ = "check_runs"
    __table_args__ = (*shop_fk(), UniqueConstraint("revision_id", "run_seq"), {"info": {"phase": "P2"}})
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("invoices.id"))
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("invoice_revisions.id"))
    run_seq: Mapped[int] = mapped_column(Integer)
    profile_version: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(12))
    inputs_hash: Mapped[str] = mapped_column(String(64))
    results_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = ts()


class CheckResult(Base):
    __tablename__ = "check_results"
    __table_args__ = (*shop_fk(), {"info": {"phase": "P2"}})
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    check_run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("check_runs.id"))
    rule_id: Mapped[str] = mapped_column(String(24))
    rule_version: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(16))
    severity: Mapped[str] = mapped_column(String(12))
    category: Mapped[str] = mapped_column(String(24))
    message: Mapped[str] = mapped_column(Text)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    calculation: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    difference: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        *shop_fk(),
        UniqueConstraint("revision_id", "rule_id"),
        CheckConstraint(
            "status IN ('open','awaiting_owner','awaiting_supplier','awaiting_ca','resolved','excluded',"
            "'superseded')"
        ),
        CheckConstraint("status <> 'superseded' OR close_reason IS NOT NULL"),
        {"info": {"phase": "P2"}},
    )
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("invoices.id"))
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("invoice_revisions.id"))
    check_result_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("check_results.id"))
    rule_id: Mapped[str] = mapped_column(String(24))
    category: Mapped[str] = mapped_column(String(24))
    blocking: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    close_reason: Mapped[str | None] = mapped_column(String(24), nullable=True)
    disposition: Mapped[str | None] = mapped_column(String(32), nullable=True)
    owner_role: Mapped[str] = mapped_column(String(12))
    next_action: Mapped[str] = mapped_column(String(255))
    due_at: Mapped[datetime | None] = ts(nullable=True)
    exposure_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    exposure_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    created_at: Mapped[datetime] = ts()
    updated_at: Mapped[datetime] = ts()


class DuplicateKey(Base):
    __tablename__ = "duplicate_keys"
    __table_args__ = (*shop_fk(), UniqueConstraint("shop_id", "key"), {"info": {"phase": "P2"}})
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    key: Mapped[str] = mapped_column(String(160))
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("invoices.id"))
    created_at: Mapped[datetime] = ts()


# --------------------------------------------------------------------------------------------- P3


class ReviewRequest(Base):
    __tablename__ = "review_requests"
    __table_args__ = (
        *shop_fk(),
        UniqueConstraint("practice_id", "public_ref"),
        CheckConstraint("status IN ('open','decided','stale')"),
        {"info": {"phase": "P3"}},
    )
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    public_ref: Mapped[str] = mapped_column(String(16))
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("invoices.id"))
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("invoice_revisions.id"))
    check_run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("check_runs.id"))
    status: Mapped[str] = mapped_column(String(8), default="open")
    created_at: Mapped[datetime] = ts()


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (*shop_fk(), {"info": {"phase": "P3"}})
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    review_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("review_requests.id"))
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("invoices.id"))
    revision_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    check_run_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    request_context_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("request_contexts.context_id"))
    action: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_issue_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    request_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = ts()


class DecisionInvalidation(Base):
    __tablename__ = "decision_invalidations"
    __table_args__ = ({"info": {"phase": "P3"}},)
    id: Mapped[uuid.UUID] = pk()
    decision_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("decisions.id"))
    reason: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = ts()


class Handoff(Base):
    __tablename__ = "handoffs"
    __table_args__ = (
        *shop_fk(),
        UniqueConstraint("dedupe_key"),
        {"info": {"phase": "P3"}},
    )
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("invoices.id"))
    expected_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    from_role: Mapped[str] = mapped_column(String(16))
    to_role: Mapped[str] = mapped_column(String(16))
    from_room: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    to_room: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    originating_actor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_refs: Mapped[list[str]] = mapped_column(JSONB, default=list)
    issue_summary: Mapped[str] = mapped_column(Text)
    responsible_role: Mapped[str] = mapped_column(String(16))
    next_action: Mapped[str] = mapped_column(String(255))
    hop_count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(12), default="pending")
    dedupe_key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = ts()


# --------------------------------------------------------------------------------------------- P4


class ShopPeriodVersion(Base):
    __tablename__ = "shop_period_versions"
    __table_args__ = ({"info": {"phase": "P4"}},)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("shops.id"), primary_key=True)
    period: Mapped[str] = mapped_column(String(10), primary_key=True)
    version: Mapped[int] = mapped_column(BigInteger, default=0)
    updated_at: Mapped[datetime] = ts()


class Snapshot(Base):
    __tablename__ = "snapshots"
    __table_args__ = (
        *shop_fk(),
        UniqueConstraint("shop_id", "period", "version"),
        UniqueConstraint("practice_id", "public_ref"),
        CheckConstraint("status IN ('draft','awaiting_ca','approved','exported','superseded','stale')"),
        {"info": {"phase": "P4"}},
    )
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    public_ref: Mapped[str] = mapped_column(String(16))
    period: Mapped[str] = mapped_column(String(7))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="awaiting_ca")
    period_version: Mapped[int] = mapped_column(BigInteger)
    unassigned_version: Mapped[int] = mapped_column(BigInteger)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB)
    manifest_bytes: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    history_cutoff: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    partial: Mapped[bool] = mapped_column(Boolean)
    acknowledged_held_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    acknowledged_unassigned_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approved_at: Mapped[datetime | None] = ts(nullable=True)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = ts()


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        *shop_fk(),
        UniqueConstraint("snapshot_id", "kind"),
        UniqueConstraint("readiness_id", "kind", name="uq_artifacts_readiness_kind"),
        {"info": {"phase": "P4"}},
    )
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("snapshots.id"), nullable=True)
    readiness_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)  # U2 purchase pack
    kind: Mapped[str] = mapped_column(String(8))
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = ts()


# --------------------------------------------------------------------------------------------- P6


class Statement(Base):
    """A user-uploaded GSTR-2B statement, stored immutably; an identical re-upload is idempotent."""

    __tablename__ = "statements"
    __table_args__ = (
        *shop_fk(),
        UniqueConstraint("shop_id", "kind", "period", "sha256"),
        UniqueConstraint("practice_id", "public_ref"),
        {"info": {"phase": "P6"}},
    )
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    public_ref: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(16), default="gstr2b")
    period: Mapped[str] = mapped_column(String(7))
    parser_version: Mapped[str] = mapped_column(String(32))
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(512))
    filename: Mapped[str] = mapped_column(String(255))
    line_count: Mapped[int] = mapped_column(Integer)
    skipped: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    imported_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = ts()


class StatementLine(Base):
    __tablename__ = "statement_lines"
    __table_args__ = (*shop_fk(), UniqueConstraint("statement_id", "line_no"), {"info": {"phase": "P6"}})
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    statement_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("statements.id"))
    line_no: Mapped[int] = mapped_column(Integer)
    supplier_gstin: Mapped[str] = mapped_column(String(15))
    supplier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_type: Mapped[str] = mapped_column(String(24))
    invoice_number: Mapped[str] = mapped_column(String(64))
    number_norm: Mapped[str] = mapped_column(String(64))
    invoice_date: Mapped[str] = mapped_column(String(10))
    financial_year: Mapped[str] = mapped_column(String(7))
    invoice_value: Mapped[Decimal] = mapped_column(MONEY)
    taxable: Mapped[Decimal] = mapped_column(MONEY)
    igst: Mapped[Decimal] = mapped_column(MONEY)
    cgst: Mapped[Decimal] = mapped_column(MONEY)
    sgst: Mapped[Decimal] = mapped_column(MONEY)
    cess: Mapped[Decimal] = mapped_column(MONEY)
    itc_available: Mapped[str | None] = mapped_column(String(8), nullable=True)


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"
    __table_args__ = (
        *shop_fk(),
        UniqueConstraint("statement_id", "run_seq"),
        UniqueConstraint("practice_id", "public_ref"),
        {"info": {"phase": "P6"}},
    )
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    public_ref: Mapped[str] = mapped_column(String(16))
    statement_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("statements.id"))
    period: Mapped[str] = mapped_column(String(7))
    run_seq: Mapped[int] = mapped_column(Integer)
    matcher_version: Mapped[str] = mapped_column(String(32))
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    results_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = ts()


class ReconciliationResult(Base):
    """One row per statement line and per purchase revision; each side appears at most once per run (P6-04)."""

    __tablename__ = "reconciliation_results"
    __table_args__ = (
        *shop_fk(),
        UniqueConstraint("run_id", "statement_line_id"),
        UniqueConstraint("run_id", "revision_id"),
        CheckConstraint("class_ IN ('exact_match','mismatch','purchase_only','statement_only','ambiguous')"),
        {"info": {"phase": "P6"}},
    )
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("reconciliation_runs.id"))
    class_: Mapped[str] = mapped_column("class_", String(16))
    statement_line_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    case_ref: Mapped[str | None] = mapped_column(String(16), nullable=True)
    key: Mapped[str] = mapped_column(String(160))
    differences: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


# --------------------------------------------------------------------------------------------- P5


class TestRun(Base):
    """Acceptance runs started from the synthetic testing room (append-only)."""

    __tablename__ = "test_runs"
    __table_args__ = ({"info": {"phase": "P5"}},)
    __test__ = False
    run_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    environment: Mapped[str] = mapped_column(String(16))
    mode: Mapped[str] = mapped_column(String(16))
    switch_versions: Mapped[str] = mapped_column(String(64))
    app_commit: Mapped[str] = mapped_column(String(64))
    fixture_version: Mapped[str] = mapped_column(String(32))
    started_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    assertions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    failures: Mapped[list[str]] = mapped_column(JSONB, default=list)
    artifact_refs: Mapped[list[str]] = mapped_column(JSONB, default=list)
    report_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = ts()


class DigestRun(Base):
    """One scheduled digest per room per local date; drives stop rules and escalation."""

    __tablename__ = "digest_runs"
    __table_args__ = (UniqueConstraint("room_binding_id", "local_date"), {"info": {"phase": "P5"}})
    id: Mapped[uuid.UUID] = pk()
    room_binding_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("room_bindings.id"))
    local_date: Mapped[str] = mapped_column(String(10))
    items: Mapped[list[str]] = mapped_column(JSONB, default=list)
    escalated: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = ts()


# --------------------------------------------------------------------------------------------- U2
# Purchase assurance (docs/purchase-assurance-update.md). Every table is shop-scoped.


class ShopCapability(Base):
    """A verified, revocable business capability of one user in one shop (D-25). Titles grant nothing."""

    __tablename__ = "shop_capabilities"
    __table_args__ = (
        *shop_fk(),
        UniqueConstraint("user_id", "shop_id", "capability"),
        CheckConstraint(
            "capability IN ('order_confirm','delivery_confirm','task_assign','task_work','invoice_view',"
            "'purchase_review','readiness_authorize','invoice_submit')"
        ),
        {"info": {"phase": "U2"}},
    )
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    capability: Mapped[str] = mapped_column(String(24))
    granted_at: Mapped[datetime] = ts()
    revoked_at: Mapped[datetime | None] = ts(nullable=True)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        *shop_fk(),
        UniqueConstraint("practice_id", "order_ref"),
        CheckConstraint("status IN ('draft','confirmed','cancelled')"),
        {"info": {"phase": "U2"}},
    )
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    order_ref: Mapped[str] = mapped_column(String(32))
    supplier_name: Mapped[str] = mapped_column(String(255))
    supplier_gstin: Mapped[str] = mapped_column(String(15))
    status: Mapped[str] = mapped_column(String(12), default="draft")
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = ts()


class PurchaseOrderRevision(Base):
    """Order contents; immutable once confirmed. Lines: [{line_id, item_code, description, ordered_qty,
    unit, unit_price, tax_basis}] with Decimal values stored as strings."""

    __tablename__ = "purchase_order_revisions"
    __table_args__ = (
        *shop_fk(),
        UniqueConstraint("order_id", "revision_no"),
        CheckConstraint("status IN ('draft','confirmed','superseded')"),
        {"info": {"phase": "U2"}},
    )
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("purchase_orders.id"))
    revision_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="draft")
    expected_delivery_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    lines: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    confirmed_at: Mapped[datetime | None] = ts(nullable=True)
    created_at: Mapped[datetime] = ts()


class DeliveryReport(Base):
    """One version of a delivery report. A confirmed newer version supersedes the older one; only current
    confirmed versions count toward the received quantity (M03, M08)."""

    __tablename__ = "delivery_reports"
    __table_args__ = (
        *shop_fk(),
        UniqueConstraint("order_id", "report_ref", "report_version"),
        CheckConstraint("status IN ('submitted','confirmed','superseded','rejected')"),
        {"info": {"phase": "U2"}},
    )
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("purchase_orders.id"))
    report_ref: Mapped[str] = mapped_column(String(16))
    report_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="submitted")
    lines: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    content_hash: Mapped[str] = mapped_column(String(64))
    submitted_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    observed_at: Mapped[datetime] = ts()
    created_at: Mapped[datetime] = ts()


class DeliveryEvent(Base):
    __tablename__ = "delivery_events"
    __table_args__ = (
        *shop_fk(),
        CheckConstraint("action IN ('submitted','confirmed','superseded','rejected')"),
        {"info": {"phase": "U2"}},
    )
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    report_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("delivery_reports.id"))
    action: Mapped[str] = mapped_column(String(12))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    context_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = ts()


class PurchaseLink(Base):
    """Invoice case <-> order. One active link per case and per order in this release (M08)."""

    __tablename__ = "purchase_links"
    __table_args__ = (
        *shop_fk(),
        CheckConstraint("status IN ('active','inactive')"),
        CheckConstraint(
            "purchase_state IN ('awaiting_evidence','needs_resolution','ready_for_review',"
            "'awaiting_owner','ready_for_payment')"
        ),
        Index(
            "uq_purchase_links_active_case", "case_id", unique=True, postgresql_where=text("status = 'active'")
        ),
        Index(
            "uq_purchase_links_active_order", "order_id", unique=True, postgresql_where=text("status = 'active'")
        ),
        {"info": {"phase": "U2"}},
    )
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("invoices.id"))
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("purchase_orders.id"))
    link_version: Mapped[int] = mapped_column(Integer, default=1)
    mapping: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)  # invoice line_no -> order line_id
    status: Mapped[str] = mapped_column(String(8), default="active")
    purchase_state: Mapped[str] = mapped_column(String(20), default="awaiting_evidence")
    partial_accepted_at: Mapped[datetime | None] = ts(nullable=True)
    partial_accepted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    confirmed_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    confirmed_at: Mapped[datetime] = ts()


class PurchaseMatchRun(Base):
    __tablename__ = "purchase_match_runs"
    __table_args__ = (
        *shop_fk(),
        UniqueConstraint("link_id", "input_hash", "rule_version"),
        CheckConstraint("status IN ('pass','hold','needs_evidence')"),
        {"info": {"phase": "U2"}},
    )
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    link_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("purchase_links.id"))
    input_vector: Mapped[dict[str, Any]] = mapped_column(JSONB)
    input_hash: Mapped[str] = mapped_column(String(64))
    rule_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    totals: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    results_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = ts()


class BusinessTask(Base):
    __tablename__ = "business_tasks"
    __table_args__ = (
        *shop_fk(),
        UniqueConstraint("practice_id", "task_ref"),
        CheckConstraint(
            "status IN ('open','acknowledged','evidence_submitted','verified_complete','cancelled','superseded')"
        ),
        {"info": {"phase": "U2"}},
    )
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    task_ref: Mapped[str] = mapped_column(String(16))
    link_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("purchase_links.id"))
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("invoices.id"))
    category: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    assignee_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    assigned_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    due_at: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="open")
    blocker: Mapped[bool] = mapped_column(Boolean, default=True)
    expected_input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = ts()
    updated_at: Mapped[datetime] = ts()


class TaskEvent(Base):
    __tablename__ = "task_events"
    __table_args__ = (*shop_fk(), {"info": {"phase": "U2"}})
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("business_tasks.id"))
    action: Mapped[str] = mapped_column(String(24))
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    context_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = ts()


class PaymentReadiness(Base):
    """A frozen purchase-review record (PR-...). Its content is fixed at creation; the reviewer's sign-off and
    the owner's authorization bind its content hash. Ready for payment never means paid."""

    __tablename__ = "payment_readiness"
    __table_args__ = (
        *shop_fk(),
        UniqueConstraint("practice_id", "public_ref"),
        CheckConstraint("status IN ('awaiting_review','awaiting_owner','ready_for_payment','stale')"),
        {"info": {"phase": "U2"}},
    )
    id: Mapped[uuid.UUID] = pk()
    practice_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    public_ref: Mapped[str] = mapped_column(String(16))
    link_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("purchase_links.id"))
    match_run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("purchase_match_runs.id"))
    input_hash: Mapped[str] = mapped_column(String(64))
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    content_hash: Mapped[str] = mapped_column(String(64))
    amount: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(20), default="awaiting_review")
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reviewed_at: Mapped[datetime | None] = ts(nullable=True)
    review_context_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    authorized_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    authorized_at: Mapped[datetime | None] = ts(nullable=True)
    authorize_context_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    due_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    due_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    stale_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = ts()


APPEND_ONLY_TABLES = (
    "documents",
    "field_evidence",
    "check_results",
    "decisions",
    "case_events",
    "audit_events",
    "statements",
    "statement_lines",
    "reconciliation_results",
    "test_runs",
    "delivery_events",
    "purchase_match_runs",
    "task_events",
)


def tables_for_phase(phase: str) -> list[Any]:
    return [t for t in Base.metadata.sorted_tables if t.info.get("phase") == phase]
