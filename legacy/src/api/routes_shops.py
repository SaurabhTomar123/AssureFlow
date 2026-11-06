from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from typing import Optional
from src.db.session import get_db
from src.db.models import Shop
from src.gst_engine.rules import validate_gstin_format

router = APIRouter(prefix="/api/shops", tags=["Shops"])


class ShopCreate(BaseModel):
    name: str
    gstin: str
    telegram_chat_id: Optional[str] = None


class ShopResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    gstin: str
    state_code: str
    telegram_chat_id: Optional[str] = None


@router.get("", response_model=list[ShopResponse])
def list_shops(db: Session = Depends(get_db)):
    return db.query(Shop).all()


@router.get("/{shop_id}", response_model=ShopResponse)
def get_shop(shop_id: str, db: Session = Depends(get_db)):
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return shop


@router.post("", response_model=ShopResponse, status_code=201)
def create_shop(payload: ShopCreate, db: Session = Depends(get_db)):
    clean_gstin = payload.gstin.strip().upper()
    valid, err = validate_gstin_format(clean_gstin)
    if not valid:
        raise HTTPException(status_code=400, detail=f"Invalid GSTIN: {err}")

    existing = db.query(Shop).filter(Shop.gstin == clean_gstin).first()
    if existing:
        raise HTTPException(status_code=400, detail="Shop with this GSTIN already exists")

    shop = Shop(
        name=payload.name.strip(),
        gstin=clean_gstin,
        state_code=clean_gstin[:2],
        telegram_chat_id=payload.telegram_chat_id,
    )
    db.add(shop)
    db.commit()
    db.refresh(shop)
    return shop
