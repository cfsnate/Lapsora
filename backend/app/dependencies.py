"""FastAPI dependencies — authentication and shared utilities."""

import logging

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User

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
