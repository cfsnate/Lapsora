"""Auth endpoints — setup wizard, login, logout, and current user."""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas import LoginRequest, SetupCreate, SetupStatusResponse, UserRead

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Setup (unauthenticated)
# ---------------------------------------------------------------------------


@router.get("/setup-status", response_model=SetupStatusResponse)
def get_setup_status(db: Session = Depends(get_db)):
    count = db.query(User).count()
    return SetupStatusResponse(setup_required=count == 0)


@router.post("/setup", response_model=UserRead, status_code=201)
def run_setup(payload: SetupCreate, db: Session = Depends(get_db)):
    count = db.query(User).count()
    if count > 0:
        raise HTTPException(status_code=409, detail="Setup has already been completed.")

    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    password_hash = bcrypt.hashpw(
        payload.password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    user = User(
        username=payload.username,
        display_name=payload.display_name,
        email=payload.email,
        password_hash=password_hash,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------


@router.post("/login", response_model=UserRead)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """Verify credentials, issue JWT in httpOnly cookie, return UserRead."""
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    try:
        valid = bcrypt.checkpw(
            payload.password.encode("utf-8"),
            user.password_hash.encode("utf-8"),
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not valid:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    exp = datetime.now(UTC) + timedelta(hours=settings.JWT_EXPIRY_HOURS)
    token = jwt.encode(
        {"sub": str(user.id), "exp": exp},
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=settings.JWT_EXPIRY_HOURS * 3600,
    )
    return user


@router.post("/logout")
def logout(response: Response):
    """Clear the access_token cookie."""
    response.set_cookie(
        key="access_token",
        value="",
        httponly=True,
        samesite="lax",
        path="/",
        max_age=0,
    )
    return {"detail": "logged_out"}


# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user."""
    return current_user
