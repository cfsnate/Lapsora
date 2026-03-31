"""FastAPI dependencies — authentication and shared utilities."""

import logging

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User, UserProfileAccess

logger = logging.getLogger(__name__)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Decode the access_token cookie and return the authenticated User.

    Raises HTTPException 401 for:
    - token missing
    - token invalid / tampered
    - token expired
    - user not found in DB
    - user is inactive
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="token_missing")

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token_expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="token_invalid")

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="token_invalid")

    try:
        user_id_int = int(user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="token_invalid")

    user = db.query(User).filter(User.id == user_id_int).first()
    if user is None:
        raise HTTPException(status_code=401, detail="token_invalid")

    if not user.is_active:
        raise HTTPException(status_code=401, detail="user_inactive")

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Raise 403 if the authenticated user is not an admin."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="admin_required")
    return current_user


def check_profile_access(user: User, profile_id: int, db: Session) -> None:
    """Raise 403 if a non-admin user has no junction row for the given profile.

    Admin users bypass this check entirely.
    """
    if user.role == "admin":
        return
    row = (
        db.query(UserProfileAccess)
        .filter(UserProfileAccess.user_id == user.id, UserProfileAccess.profile_id == profile_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=403, detail="profile_access_denied")


def get_accessible_profile_ids(user: User, db: Session) -> list[int] | None:
    """Return None for admins (meaning 'all'), or a list of profile IDs for non-admins."""
    if user.role == "admin":
        return None
    rows = db.query(UserProfileAccess).filter(UserProfileAccess.user_id == user.id).all()
    return [row.profile_id for row in rows]
