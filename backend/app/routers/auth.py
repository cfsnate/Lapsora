"""Auth endpoints — setup wizard, login, logout, current user, and OIDC."""

import logging
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import decrypt, encrypt, settings
from app.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models import Setting, User
from app.schemas import (
    LoginRequest,
    OIDCConfigRead,
    OIDCConfigUpdate,
    SetupCreate,
    SetupStatusResponse,
    UserRead,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# OIDC helpers
# ---------------------------------------------------------------------------


def _get_oidc_client(db: Session) -> tuple[OAuth, str]:
    """Read OIDC config from settings table and return a configured OAuth client + provider name."""
    issuer_row = db.query(Setting).filter(Setting.key == "oidc_issuer_url").first()
    client_id_row = db.query(Setting).filter(Setting.key == "oidc_client_id").first()
    client_secret_row = db.query(Setting).filter(Setting.key == "oidc_client_secret").first()
    provider_name_row = db.query(Setting).filter(Setting.key == "oidc_provider_name").first()

    if not issuer_row or not client_id_row or not client_secret_row:
        raise HTTPException(status_code=400, detail="oidc_not_configured")

    try:
        client_secret = decrypt(client_secret_row.value)
    except Exception:
        raise HTTPException(status_code=500, detail="oidc_config_corrupt")

    provider_name = provider_name_row.value if provider_name_row else "oidc"
    issuer_url = issuer_row.value.rstrip("/")

    try:
        oauth = OAuth()
        oauth.register(
            name="oidc",
            client_id=client_id_row.value,
            client_secret=client_secret,
            server_metadata_url=f"{issuer_url}/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
    except Exception as exc:
        logger.warning("OIDC provider discovery failed: %s", exc)
        raise HTTPException(status_code=500, detail="oidc_provider_unavailable")

    return oauth, provider_name


def _issue_jwt_cookie(response: Response, user: User) -> None:
    """Issue a JWT httpOnly cookie using the same pattern as local login."""
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


def _provision_user(db: Session, userinfo: dict, provider_name: str) -> User:
    """Find existing OIDC user or auto-provision a new one."""
    subject = userinfo.get("sub")
    if not subject:
        raise HTTPException(status_code=401, detail="oidc_callback_failed")

    # Check for existing linked account
    user = (
        db.query(User)
        .filter(User.oidc_provider == provider_name, User.oidc_subject == subject)
        .first()
    )
    if user:
        return user

    # Auto-provision a new user
    email = userinfo.get("email")
    preferred_username = userinfo.get("preferred_username") or (
        email.split("@")[0] if email else None
    ) or f"oidc_{subject[:12]}"

    # Sanitize username: keep alphanumeric, underscore, hyphen
    base_username = "".join(c for c in preferred_username if c.isalnum() or c in "_-")[:64] or "oidc_user"

    # Collision handling: append _oidc then numeric suffix
    username = base_username
    if db.query(User).filter(User.username == username).first():
        username = f"{base_username}_oidc"
    counter = 1
    while db.query(User).filter(User.username == username).first():
        username = f"{base_username}_oidc{counter}"
        counter += 1

    display_name = userinfo.get("name") or username

    user = User(
        username=username,
        display_name=display_name,
        email=email,
        password_hash="!",  # sentinel — bcrypt.checkpw always fails
        role="user",
        is_active=True,
        oidc_provider=provider_name,
        oidc_subject=subject,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(
        "OIDC user created: %s provider=%s subject=%s", user.username, provider_name, subject
    )
    return user


# ---------------------------------------------------------------------------
# OIDC config endpoints
# ---------------------------------------------------------------------------


@router.get("/oidc/config", response_model=OIDCConfigRead)
def get_oidc_config(db: Session = Depends(get_db)):
    """Return OIDC config status (public — no auth required)."""
    issuer_row = db.query(Setting).filter(Setting.key == "oidc_issuer_url").first()
    provider_name_row = db.query(Setting).filter(Setting.key == "oidc_provider_name").first()

    if not issuer_row:
        return OIDCConfigRead(enabled=False)

    return OIDCConfigRead(
        enabled=True,
        provider_name=provider_name_row.value if provider_name_row else None,
        issuer_url=issuer_row.value,
    )


@router.put("/oidc/config", response_model=OIDCConfigRead)
def put_oidc_config(
    payload: OIDCConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Save OIDC provider config (admin-only)."""

    encrypted_secret = encrypt(payload.client_secret)

    def _upsert(key: str, value: str) -> None:
        row = db.query(Setting).filter(Setting.key == key).first()
        if row:
            row.value = value
        else:
            db.add(Setting(key=key, value=value))

    _upsert("oidc_issuer_url", payload.issuer_url)
    _upsert("oidc_client_id", payload.client_id)
    _upsert("oidc_client_secret", encrypted_secret)
    if payload.provider_name is not None:
        _upsert("oidc_provider_name", payload.provider_name)
    db.commit()

    return OIDCConfigRead(
        enabled=True,
        provider_name=payload.provider_name,
        issuer_url=payload.issuer_url,
    )


# ---------------------------------------------------------------------------
# OIDC login / callback
# ---------------------------------------------------------------------------


@router.get("/oidc/login")
async def oidc_login(request: Request, db: Session = Depends(get_db)):
    """Redirect the browser to the OIDC provider's authorization endpoint."""
    try:
        oauth, _provider_name = _get_oidc_client(db)
    except HTTPException:
        raise

    redirect_uri = str(request.url_for("oidc_callback"))
    try:
        return await oauth.oidc.authorize_redirect(request, redirect_uri)
    except Exception as exc:
        logger.warning("OIDC provider unavailable during login: %s", exc)
        raise HTTPException(status_code=500, detail="oidc_provider_unavailable")


@router.get("/oidc/callback", name="oidc_callback")
async def oidc_callback(request: Request, db: Session = Depends(get_db)):
    """Handle the OIDC provider callback, provision user, issue cookie, redirect to /."""
    # Missing state param → 401
    if not request.query_params.get("state") and not request.session.get("_state_oidc_state"):
        # Authlib stores state in session; if both are absent, request is invalid
        # Let authorize_access_token raise for us — just check the obvious case
        pass

    try:
        oauth, provider_name = _get_oidc_client(db)
    except HTTPException as exc:
        raise HTTPException(status_code=401, detail="oidc_callback_failed") from exc

    try:
        token = await oauth.oidc.authorize_access_token(request)
    except Exception as exc:
        logger.warning("OIDC callback token exchange failed: %s", exc)
        raise HTTPException(status_code=401, detail="oidc_callback_failed")

    try:
        userinfo = token.get("userinfo") or await oauth.oidc.userinfo(token=token)
    except Exception as exc:
        logger.warning("OIDC userinfo fetch failed: %s", exc)
        raise HTTPException(status_code=401, detail="oidc_callback_failed")

    try:
        user = _provision_user(db, userinfo, provider_name)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("OIDC user provisioning failed: %s", exc)
        raise HTTPException(status_code=401, detail="oidc_callback_failed")

    logger.info("OIDC login: user_id=%d provider=%s", user.id, provider_name)

    response = RedirectResponse(url="/")
    _issue_jwt_cookie(response, user)
    return response
