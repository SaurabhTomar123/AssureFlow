from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from src.db.session import get_db
from src.db.models import Shop
from src.users.service import create_user_profile, list_shop_users, get_user_profile

router = APIRouter(prefix="/api/users", tags=["User Profiles & RBAC"])


class UserProfileCreate(BaseModel):
    shop_id: str
    name: str
    role: str = "STAFF"
    telegram_user_id: Optional[str] = None
    phone: Optional[str] = None


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    shop_id: str
    name: str
    role: str
    telegram_user_id: Optional[str] = None
    phone: Optional[str] = None
    is_active: bool


@router.post("", response_model=UserProfileResponse, status_code=201)
def add_user(payload: UserProfileCreate, db: Session = Depends(get_db)):
    shop = db.query(Shop).filter(Shop.id == payload.shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    return create_user_profile(
        shop_id=payload.shop_id,
        name=payload.name,
        role=payload.role,
        telegram_user_id=payload.telegram_user_id,
        phone=payload.phone,
        db=db,
    )


@router.get("/{shop_id}", response_model=list[UserProfileResponse])
def get_users(shop_id: str, db: Session = Depends(get_db)):
    return list_shop_users(shop_id, db)

