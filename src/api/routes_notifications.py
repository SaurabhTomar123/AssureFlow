from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.db.models import Shop
from src.notifications.alert_engine import get_proactive_store_alerts

router = APIRouter(prefix="/api/notifications", tags=["Proactive Notifications"])


@router.get("/alerts/{shop_id}")
def get_store_alerts(shop_id: str, db: Session = Depends(get_db)):
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return get_proactive_store_alerts(shop_id, db)
