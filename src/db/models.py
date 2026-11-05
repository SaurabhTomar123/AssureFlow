import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import relationship
from src.db.session import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    pan = Column(String(10), nullable=True)
    gstin = Column(String(15), nullable=True)
    tier = Column(String(32), default="GROWTH")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    shops = relationship("Shop", back_populates="tenant")
    users = relationship("OrganizationUser", back_populates="tenant", cascade="all, delete-orphan")


class Shop(Base):
    __tablename__ = "shops"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=True)
    name = Column(String(255), nullable=False)
    gstin = Column(String(15), nullable=False, unique=True)
    state_code = Column(String(2), nullable=False)
    telegram_chat_id = Column(String(64), nullable=True, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="shops")
    bills = relationship("Bill", back_populates="shop", cascade="all, delete-orphan")
    issues = relationship("ComplianceIssueModel", back_populates="shop", cascade="all, delete-orphan")


class Bill(Base):
    __tablename__ = "bills"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_type = Column(String(32), default="pdf")

    supplier_name = Column(String(255), nullable=True)
    supplier_gstin = Column(String(15), nullable=True)
    supplier_state_code = Column(String(2), nullable=True)
    bill_number = Column(String(64), nullable=True)
    bill_date = Column(String(32), nullable=True)

    taxable_amount = Column(Float, default=0.0)
    cgst_amount = Column(Float, default=0.0)
    sgst_amount = Column(Float, default=0.0)
    igst_amount = Column(Float, default=0.0)
    total_amount = Column(Float, default=0.0)

    is_confirmed_by_owner = Column(Boolean, default=False)
    document_category = Column(String(32), default="PAKKA_TAX_INVOICE")
    status = Column(String(32), default="pending_review")
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="bills")
    items = relationship("BillItem", back_populates="bill", cascade="all, delete-orphan")
    issues = relationship("ComplianceIssueModel", back_populates="bill", cascade="all, delete-orphan")


class BillItem(Base):
    __tablename__ = "bill_items"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    bill_id = Column(String(36), ForeignKey("bills.id"), nullable=False)
    description = Column(String(255), nullable=False)
    hsn_code = Column(String(32), nullable=True)
    quantity = Column(Float, default=1.0)
    rate = Column(Float, default=0.0)
    tax_rate_percent = Column(Float, default=0.0)
    taxable_value = Column(Float, default=0.0)
    cgst = Column(Float, default=0.0)
    sgst = Column(Float, default=0.0)
    igst = Column(Float, default=0.0)
    total = Column(Float, default=0.0)

    bill = relationship("Bill", back_populates="items")


class ComplianceIssueModel(Base):
    __tablename__ = "compliance_issues"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    bill_id = Column(String(36), ForeignKey("bills.id"), nullable=False)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)

    issue_type = Column(String(64), nullable=False)
    severity = Column(String(16), nullable=False)
    rupee_value_at_risk = Column(Float, default=0.0)
    explanation = Column(Text, nullable=False)
    suggested_action = Column(Text, nullable=True)

    ca_action = Column(String(32), default="pending")
    supplier_inquiry_draft = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    bill = relationship("Bill", back_populates="issues")
    shop = relationship("Shop", back_populates="issues")


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    bill_id = Column(String(36), ForeignKey("bills.id"), nullable=True)

    category = Column(String(64), nullable=False)
    description = Column(String(255), nullable=False)
    amount = Column(Float, default=0.0)
    tax_amount = Column(Float, default=0.0)
    total_outflow = Column(Float, default=0.0)
    entry_date = Column(String(32), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop")
    bill = relationship("Bill")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    telegram_user_id = Column(String(64), nullable=True)
    name = Column(String(128), nullable=False)
    phone = Column(String(32), nullable=True)
    role = Column(String(32), nullable=False, default="STAFF")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop")


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    sku = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    category = Column(String(64), nullable=False, default="General")
    unit = Column(String(32), nullable=False, default="units")
    current_stock = Column(Float, default=0.0)
    reorder_level = Column(Float, default=10.0)
    cost_price = Column(Float, default=0.0)
    selling_price = Column(Float, default=0.0)
    hsn_code = Column(String(32), nullable=True)
    last_restocked_at = Column(DateTime, nullable=True)

    shop = relationship("Shop")
    movements = relationship("StockMovement", back_populates="item", cascade="all, delete-orphan")


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    item_id = Column(String(36), ForeignKey("inventory_items.id"), nullable=False)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    movement_type = Column(String(32), nullable=False)
    quantity = Column(Float, nullable=False)
    reference_bill_id = Column(String(36), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    item = relationship("InventoryItem", back_populates="movements")


class Employee(Base):
    __tablename__ = "employees"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    name = Column(String(128), nullable=False)
    designation = Column(String(64), nullable=False, default="Staff")
    wage_type = Column(String(32), nullable=False, default="MONTHLY")
    base_rate = Column(Float, default=15000.0)
    joining_date = Column(String(32), nullable=False, default="2026-01-01")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop")
    attendance = relationship("AttendanceRecord", back_populates="employee", cascade="all, delete-orphan")
    payroll = relationship("PayrollRecord", back_populates="employee", cascade="all, delete-orphan")


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    employee_id = Column(String(36), ForeignKey("employees.id"), nullable=False)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    date = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="PRESENT")
    check_in_time = Column(String(32), nullable=True)
    check_out_time = Column(String(32), nullable=True)
    overtime_hours = Column(Float, default=0.0)
    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    employee = relationship("Employee", back_populates="attendance")


class PayrollRecord(Base):
    __tablename__ = "payroll_records"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    employee_id = Column(String(36), ForeignKey("employees.id"), nullable=False)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    working_days_in_month = Column(Integer, default=30)
    days_present = Column(Float, default=0.0)
    days_absent = Column(Float, default=0.0)
    gross_salary = Column(Float, default=0.0)
    advances_deducted = Column(Float, default=0.0)
    net_payable = Column(Float, default=0.0)
    is_paid = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    employee = relationship("Employee", back_populates="payroll")


class OrganizationUser(Base):
    __tablename__ = "organization_users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=True)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(String(32), default="STORE_MANAGER")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    tenant = relationship("Tenant", back_populates="users")
    shop = relationship("Shop")


class GSTR2BInwardRecord(Base):
    __tablename__ = "gstr2b_inward_records"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=True)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=True)
    supplier_gstin = Column(String(15), nullable=False)
    supplier_trade_name = Column(String(255), nullable=True)
    invoice_number = Column(String(64), nullable=False)
    invoice_date = Column(String(32), nullable=False)
    invoice_value = Column(Float, default=0.0)
    taxable_value = Column(Float, default=0.0)
    igst = Column(Float, default=0.0)
    cgst = Column(Float, default=0.0)
    sgst = Column(Float, default=0.0)
    cess = Column(Float, default=0.0)
    filing_period = Column(String(16), nullable=False)
    filing_date = Column(String(32), nullable=True)
    itc_eligibility = Column(String(32), default="Y")
    match_status = Column(String(32), default="UNMATCHED")
    matched_bill_id = Column(String(36), ForeignKey("bills.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop")
    matched_bill = relationship("Bill")


class BankTransaction(Base):
    __tablename__ = "bank_transactions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=True)
    shop_id = Column(String(36), ForeignKey("shops.id"), nullable=False)
    account_number = Column(String(32), nullable=False)
    txn_date = Column(String(32), nullable=False)
    narration = Column(String(512), nullable=False)
    txn_type = Column(String(16), nullable=False)
    amount = Column(Float, default=0.0)
    mode = Column(String(32), default="UPI")
    reference_no = Column(String(64), nullable=True)
    recon_status = Column(String(32), default="UNRECONCILED")
    matched_bill_id = Column(String(36), ForeignKey("bills.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop")
    matched_bill = relationship("Bill")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=True)
    user_id = Column(String(36), nullable=True)
    action = Column(String(64), nullable=False)
    resource_type = Column(String(64), nullable=False)
    resource_id = Column(String(64), nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)


