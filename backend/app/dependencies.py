"""FastAPI dependencies — authentication and shared utilities."""

import logging
from typing import Literal

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import GroupProfileAccess, User, UserGroupMembership, UserProfileAccess

logger = logging.getLogger(__name__)

# Permission flag names that can be checked
Permission = Literal["can_view", "can_export", "can_timelapse", "can_manage"]


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


# ---------------------------------------------------------------------------
# Permission resolution helpers
# ---------------------------------------------------------------------------

def _get_user_group_ids(user_id: int, db: Session) -> list[int]:
    """Return group IDs the user belongs to via user_group_membership."""
    rows = db.query(UserGroupMembership.group_id).filter(
        UserGroupMembership.user_id == user_id
    ).all()
    return [r[0] for r in rows]


def get_profile_permissions(user: User, profile_id: int, db: Session) -> dict[str, bool]:
    """Return merged permission flags for a user+profile.

    Merges direct user access + group access (via user_group_membership).
    Any-grant-wins: if *any* source grants a permission, the result is True.
    Returns {"can_view": False, ...} if the user has no access at all.
    """
    perms = {"can_view": False, "can_export": False, "can_timelapse": False, "can_manage": False}

    # Direct user access
    direct = (
        db.query(UserProfileAccess)
        .filter(UserProfileAccess.user_id == user.id, UserProfileAccess.profile_id == profile_id)
        .first()
    )
    if direct:
        for key in perms:
            if getattr(direct, key, False):
                perms[key] = True

    # Group access
    group_ids = _get_user_group_ids(user.id, db)
    if group_ids:
        group_rows = (
            db.query(GroupProfileAccess)
            .filter(
                GroupProfileAccess.group_id.in_(group_ids),
                GroupProfileAccess.profile_id == profile_id,
            )
            .all()
        )
        for row in group_rows:
            for key in perms:
                if getattr(row, key, False):
                    perms[key] = True

    return perms


def check_profile_permission(user: User, profile_id: int, permission: Permission, db: Session) -> None:
    """Raise 403 if the user lacks a specific permission on the profile.

    Admin users bypass all checks.
    """
    if user.role == "admin":
        return
    perms = get_profile_permissions(user, profile_id, db)
    if not perms.get(permission, False):
        raise HTTPException(status_code=403, detail="profile_access_denied")


def check_profile_access(user: User, profile_id: int, db: Session) -> None:
    """Raise 403 if the user cannot view the profile.

    Admin users bypass this check entirely.
    """
    check_profile_permission(user, profile_id, "can_view", db)


def get_accessible_profile_ids(user: User, db: Session) -> list[int] | None:
    """Return None for admins (meaning 'all'), or a deduplicated list of
    profile IDs the user can view (direct + group access)."""
    if user.role == "admin":
        return None

    profile_ids: set[int] = set()

    # Direct access
    direct_rows = (
        db.query(UserProfileAccess.profile_id)
        .filter(UserProfileAccess.user_id == user.id, UserProfileAccess.can_view == True)  # noqa: E712
        .all()
    )
    profile_ids.update(r[0] for r in direct_rows)

    # Group access
    group_ids = _get_user_group_ids(user.id, db)
    if group_ids:
        group_rows = (
            db.query(GroupProfileAccess.profile_id)
            .filter(
                GroupProfileAccess.group_id.in_(group_ids),
                GroupProfileAccess.can_view == True,  # noqa: E712
            )
            .all()
        )
        profile_ids.update(r[0] for r in group_rows)

    return sorted(profile_ids)
