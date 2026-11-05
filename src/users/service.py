from typing import Optional, List
from sqlalchemy.orm import Session
from src.db.models import UserProfile, Shop


def create_user_profile(
    shop_id: str,
    name: str,
    role: str = "STAFF",
    telegram_user_id: Optional[str] = None,
    phone: Optional[str] = None,
    db: Session = None,
) -> UserProfile:
    normalized_role = role.strip().upper()
    if normalized_role not in ["OWNER", "MANAGER", "STAFF", "CA"]:
        normalized_role = "STAFF"

    profile = UserProfile(
        shop_id=shop_id,
        name=name.strip(),
        role=normalized_role,
        telegram_user_id=telegram_user_id,
        phone=phone,
        is_active=True,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def get_user_by_telegram_id(shop_id: str, telegram_user_id: str, db: Session) -> Optional[UserProfile]:
    return (
        db.query(UserProfile)
        .filter(UserProfile.shop_id == shop_id, UserProfile.telegram_user_id == str(telegram_user_id))
        .first()
    )


def list_shop_users(shop_id: str, db: Session) -> List[UserProfile]:
    return db.query(UserProfile).filter(UserProfile.shop_id == shop_id).all()


def get_user_profile(user_id: str, db: Session) -> Optional[UserProfile]:
    return db.query(UserProfile).filter(UserProfile.id == user_id).first()
