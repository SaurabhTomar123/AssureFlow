from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.db.models import Tenant, OrganizationUser, Shop
from src.auth.jwt_handler import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_current_user,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication & Multi-Tenancy"])


class RegisterTenantRequest(BaseModel):
    tenant_name: str
    pan: Optional[str] = None
    gstin: Optional[str] = None
    admin_email: EmailStr
    admin_password: str
    admin_full_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    full_name: str
    role: str
    tenant_id: str
    tenant_name: str
    shop_id: Optional[str] = None


class UserProfileResponse(BaseModel):
    user_id: str
    email: str
    full_name: str
    role: str
    tenant_id: str
    tenant_name: str
    shop_id: Optional[str] = None
    is_active: bool


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register_tenant(req: RegisterTenantRequest, db: Session = Depends(get_db)):
    existing_user = db.query(OrganizationUser).filter(OrganizationUser.email == req.admin_email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists",
        )

    tenant = Tenant(
        name=req.tenant_name,
        pan=req.pan,
        gstin=req.gstin,
    )
    db.add(tenant)
    db.flush()

    user = OrganizationUser(
        tenant_id=tenant.id,
        email=req.admin_email,
        hashed_password=get_password_hash(req.admin_password),
        full_name=req.admin_full_name,
        role="TENANT_ADMIN",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(tenant)
    db.refresh(user)

    token = create_access_token(
        data={
            "sub": user.id,
            "tenant_id": tenant.id,
            "role": user.role,
            "email": user.email,
        }
    )

    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        shop_id=user.shop_id,
    )


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(OrganizationUser).filter(OrganizationUser.email == req.email).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    tenant_name = tenant.name if tenant else "Default Organization"

    token = create_access_token(
        data={
            "sub": user.id,
            "tenant_id": user.tenant_id,
            "role": user.role,
            "email": user.email,
        }
    )

    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        tenant_id=user.tenant_id,
        tenant_name=tenant_name,
        shop_id=user.shop_id,
    )


@router.get("/me", response_model=UserProfileResponse)
def get_authenticated_profile(
    current_user: OrganizationUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    tenant_name = tenant.name if tenant else "Default Organization"

    return UserProfileResponse(
        user_id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        tenant_id=current_user.tenant_id,
        tenant_name=tenant_name,
        shop_id=current_user.shop_id,
        is_active=current_user.is_active,
    )
