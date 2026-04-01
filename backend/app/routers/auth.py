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
from app.models import Group, GroupProfileAccess, OIDCGroupMapping, Profile, Setting, User, UserGroupMembership, UserProfileAccess
from app.schemas import (
    GroupCreate,
    GroupRead,
    GroupUpdate,
    LoginRequest,
    OIDCConfigRead,
    OIDCConfigUpdate,
    ProfilePermission,
    SelfUpdate,
    SetupCreate,
    SetupStatusResponse,
    UserAdminRead,
    UserCreate,
    UserGroupMembershipUpdate,
    UserProfileAccessUpdate,
    UserRead,
    UserUpdate,
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


@router.put("/me", response_model=UserRead)
def update_me(
    payload: SelfUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Allow an authenticated user to update their own display_name, email, or password."""
    if payload.display_name is not None:
        current_user.display_name = payload.display_name
    if payload.email is not None:
        current_user.email = payload.email
    if payload.password is not None:
        current_user.password_hash = bcrypt.hashpw(
            payload.password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
    db.commit()
    db.refresh(current_user)
    return current_user


# ---------------------------------------------------------------------------
# Admin user management helpers
# ---------------------------------------------------------------------------


def _build_admin_read(user: User, db: Session) -> UserAdminRead:
    """Build a UserAdminRead by querying the junction table for profile IDs and permissions."""
    rows = db.query(UserProfileAccess).filter(UserProfileAccess.user_id == user.id).all()
    profile_ids = [row.profile_id for row in rows]
    profile_permissions = [
        ProfilePermission(
            profile_id=row.profile_id,
            can_view=row.can_view,
            can_export=row.can_export,
            can_timelapse=row.can_timelapse,
            can_manage=row.can_manage,
        )
        for row in rows
    ]
    group_rows = db.query(UserGroupMembership).filter(UserGroupMembership.user_id == user.id).all()
    return UserAdminRead(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        oidc_provider=user.oidc_provider,
        created_at=user.created_at,
        updated_at=user.updated_at,
        accessible_profile_ids=profile_ids,
        profile_permissions=profile_permissions,
        group_ids=[row.group_id for row in group_rows],
    )


# ---------------------------------------------------------------------------
# Admin user CRUD endpoints
# ---------------------------------------------------------------------------


@router.get("/users", response_model=list[UserAdminRead])
def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """List all users with their accessible profile IDs (admin-only)."""
    users = db.query(User).all()
    return [_build_admin_read(u, db) for u in users]


@router.post("/users", response_model=UserAdminRead, status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Create a new user (admin-only). Returns 409 if username already exists."""
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=409, detail="username_taken")

    if payload.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="invalid_role")

    password_hash = bcrypt.hashpw(
        payload.password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    user = User(
        username=payload.username,
        display_name=payload.display_name,
        email=payload.email,
        password_hash=password_hash,
        role=payload.role,
        is_active=payload.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _build_admin_read(user, db)


@router.get("/users/{user_id}", response_model=UserAdminRead)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Get a single user by ID (admin-only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    return _build_admin_read(user, db)


@router.put("/users/{user_id}", response_model=UserAdminRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Update a user (admin-only). Hashes password if provided."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_found")

    if payload.role is not None and payload.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="invalid_role")

    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.email is not None:
        user.email = payload.email
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.password is not None:
        user.password_hash = bcrypt.hashpw(
            payload.password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    db.commit()
    db.refresh(user)
    return _build_admin_read(user, db)


@router.delete("/users/{user_id}", response_model=UserAdminRead)
def disable_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Disable a user (set is_active=False). Admins cannot disable themselves."""
    if admin.id == user_id:
        raise HTTPException(status_code=400, detail="cannot_disable_self")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_found")

    user.is_active = False
    db.commit()
    db.refresh(user)
    return _build_admin_read(user, db)


# ---------------------------------------------------------------------------
# Profile access management endpoints
# ---------------------------------------------------------------------------


@router.get("/users/{user_id}/profiles")
def get_user_profiles(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Get profile access with permissions for a user (admin-only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_found")

    rows = db.query(UserProfileAccess).filter(UserProfileAccess.user_id == user_id).all()
    return {
        "profile_ids": [row.profile_id for row in rows],
        "profile_permissions": [
            ProfilePermission(
                profile_id=row.profile_id,
                can_view=row.can_view,
                can_export=row.can_export,
                can_timelapse=row.can_timelapse,
                can_manage=row.can_manage,
            ).model_dump()
            for row in rows
        ],
    }


@router.put("/users/{user_id}/profiles")
def set_user_profiles(
    user_id: int,
    payload: UserProfileAccessUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Set profile access for a user. Replaces all existing rows (admin-only).

    Accepts either legacy profile_ids (all default permissions) or
    profile_permissions (explicit per-profile flags). If both are provided,
    profile_permissions takes precedence for any profile_id in both lists.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_found")

    # Build a permissions map: profile_id -> permission flags
    perms_map: dict[int, ProfilePermission] = {}
    for pp in payload.profile_permissions:
        perms_map[pp.profile_id] = pp
    for pid in payload.profile_ids:
        if pid not in perms_map:
            perms_map[pid] = ProfilePermission(profile_id=pid)

    all_profile_ids = list(perms_map.keys())

    # Validate all profile IDs exist
    if all_profile_ids:
        existing_ids = {
            row.id
            for row in db.query(Profile.id)
            .filter(Profile.id.in_(all_profile_ids))
            .all()
        }
        missing = set(all_profile_ids) - existing_ids
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"profile_ids_not_found: {sorted(missing)}",
            )

    # Replace access rows
    db.query(UserProfileAccess).filter(UserProfileAccess.user_id == user_id).delete()
    for pid, pp in perms_map.items():
        db.add(UserProfileAccess(
            user_id=user_id,
            profile_id=pid,
            can_view=pp.can_view,
            can_export=pp.can_export,
            can_timelapse=pp.can_timelapse,
            can_manage=pp.can_manage,
        ))
    db.commit()

    return {
        "profile_ids": all_profile_ids,
        "profile_permissions": [pp.model_dump() for pp in perms_map.values()],
    }


# ---------------------------------------------------------------------------
# Group management helpers
# ---------------------------------------------------------------------------


def _build_group_read(group: Group, db: Session) -> GroupRead:
    """Build a GroupRead by querying junction tables for profile IDs, permissions, OIDC mappings, and members."""
    profile_rows = db.query(GroupProfileAccess).filter(GroupProfileAccess.group_id == group.id).all()
    mapping_rows = db.query(OIDCGroupMapping).filter(OIDCGroupMapping.group_id == group.id).all()
    member_rows = db.query(UserGroupMembership).filter(UserGroupMembership.group_id == group.id).all()
    return GroupRead(
        id=group.id,
        name=group.name,
        role=group.role,
        profile_ids=[row.profile_id for row in profile_rows],
        profile_permissions=[
            ProfilePermission(
                profile_id=row.profile_id,
                can_view=row.can_view,
                can_export=row.can_export,
                can_timelapse=row.can_timelapse,
                can_manage=row.can_manage,
            )
            for row in profile_rows
        ],
        oidc_group_names=[row.oidc_group_name for row in mapping_rows],
        member_user_ids=[row.user_id for row in member_rows],
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


# ---------------------------------------------------------------------------
# Group CRUD endpoints (admin-only)
# ---------------------------------------------------------------------------


@router.get("/groups", response_model=list[GroupRead])
def list_groups(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """List all groups with their profile IDs and OIDC mapping names."""
    groups = db.query(Group).all()
    return [_build_group_read(g, db) for g in groups]


@router.post("/groups", response_model=GroupRead, status_code=201)
def create_group(
    payload: GroupCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Create a group with optional profile access and OIDC mappings."""
    if db.query(Group).filter(Group.name == payload.name).first():
        raise HTTPException(status_code=409, detail="group_name_taken")

    if payload.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="invalid_role")

    # Validate profile IDs exist (from both profile_ids and profile_permissions)
    all_pids = set(payload.profile_ids) | {pp.profile_id for pp in payload.profile_permissions}
    if all_pids:
        existing = {r.id for r in db.query(Profile.id).filter(Profile.id.in_(all_pids)).all()}
        missing = all_pids - existing
        if missing:
            raise HTTPException(status_code=400, detail=f"profile_ids_not_found: {sorted(missing)}")

    # Check for OIDC group name conflicts
    if payload.oidc_group_names:
        conflicts = (
            db.query(OIDCGroupMapping)
            .filter(OIDCGroupMapping.oidc_group_name.in_(payload.oidc_group_names))
            .all()
        )
        if conflicts:
            taken = [c.oidc_group_name for c in conflicts]
            raise HTTPException(status_code=409, detail=f"oidc_group_names_taken: {taken}")

    group = Group(name=payload.name, role=payload.role)
    db.add(group)
    db.flush()  # get group.id

    # Build permissions map: profile_permissions takes precedence over bare profile_ids
    perms_map: dict[int, ProfilePermission] = {}
    for pp in payload.profile_permissions:
        perms_map[pp.profile_id] = pp
    for pid in payload.profile_ids:
        if pid not in perms_map:
            perms_map[pid] = ProfilePermission(profile_id=pid)

    for pid, pp in perms_map.items():
        db.add(GroupProfileAccess(
            group_id=group.id,
            profile_id=pid,
            can_view=pp.can_view,
            can_export=pp.can_export,
            can_timelapse=pp.can_timelapse,
            can_manage=pp.can_manage,
        ))
    for name in payload.oidc_group_names:
        db.add(OIDCGroupMapping(group_id=group.id, oidc_group_name=name))

    db.commit()
    db.refresh(group)
    return _build_group_read(group, db)


@router.put("/groups/{group_id}", response_model=GroupRead)
def update_group(
    group_id: int,
    payload: GroupUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Update a group's name, role, profile access, and/or OIDC mappings."""
    group = db.query(Group).filter(Group.id == group_id).first()
    if group is None:
        raise HTTPException(status_code=404, detail="group_not_found")

    if payload.name is not None:
        existing = db.query(Group).filter(Group.name == payload.name, Group.id != group_id).first()
        if existing:
            raise HTTPException(status_code=409, detail="group_name_taken")
        group.name = payload.name

    if payload.role is not None:
        if payload.role not in ("admin", "user"):
            raise HTTPException(status_code=400, detail="invalid_role")
        group.role = payload.role

    if payload.profile_ids is not None or payload.profile_permissions is not None:
        # Build permissions map from both fields
        perms_map: dict[int, ProfilePermission] = {}
        if payload.profile_permissions:
            for pp in payload.profile_permissions:
                perms_map[pp.profile_id] = pp
        if payload.profile_ids is not None:
            for pid in payload.profile_ids:
                if pid not in perms_map:
                    perms_map[pid] = ProfilePermission(profile_id=pid)

        all_pids = list(perms_map.keys())
        if all_pids:
            existing = {r.id for r in db.query(Profile.id).filter(Profile.id.in_(all_pids)).all()}
            missing = set(all_pids) - existing
            if missing:
                raise HTTPException(status_code=400, detail=f"profile_ids_not_found: {sorted(missing)}")

        db.query(GroupProfileAccess).filter(GroupProfileAccess.group_id == group_id).delete()
        for pid, pp in perms_map.items():
            db.add(GroupProfileAccess(
                group_id=group_id,
                profile_id=pid,
                can_view=pp.can_view,
                can_export=pp.can_export,
                can_timelapse=pp.can_timelapse,
                can_manage=pp.can_manage,
            ))

    if payload.oidc_group_names is not None:
        # Check conflicts with OTHER groups
        if payload.oidc_group_names:
            conflicts = (
                db.query(OIDCGroupMapping)
                .filter(
                    OIDCGroupMapping.oidc_group_name.in_(payload.oidc_group_names),
                    OIDCGroupMapping.group_id != group_id,
                )
                .all()
            )
            if conflicts:
                taken = [c.oidc_group_name for c in conflicts]
                raise HTTPException(status_code=409, detail=f"oidc_group_names_taken: {taken}")

        db.query(OIDCGroupMapping).filter(OIDCGroupMapping.group_id == group_id).delete()
        for name in payload.oidc_group_names:
            db.add(OIDCGroupMapping(group_id=group_id, oidc_group_name=name))

    db.commit()
    db.refresh(group)
    return _build_group_read(group, db)


@router.delete("/groups/{group_id}", status_code=204)
def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Delete a group and its profile access + OIDC mappings (cascade)."""
    group = db.query(Group).filter(Group.id == group_id).first()
    if group is None:
        raise HTTPException(status_code=404, detail="group_not_found")

    db.delete(group)
    db.commit()
    return None


# ---------------------------------------------------------------------------
# User group membership (admin-only)
# ---------------------------------------------------------------------------


@router.get("/users/{user_id}/groups")
def get_user_groups(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Get groups the user belongs to (admin-only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_found")

    rows = db.query(UserGroupMembership).filter(UserGroupMembership.user_id == user_id).all()
    return {"group_ids": [row.group_id for row in rows]}


@router.put("/users/{user_id}/groups")
def set_user_groups(
    user_id: int,
    payload: UserGroupMembershipUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Set group membership for a user. Replaces all existing rows (admin-only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_found")

    # Validate group IDs exist
    if payload.group_ids:
        existing_ids = {r.id for r in db.query(Group.id).filter(Group.id.in_(payload.group_ids)).all()}
        missing = set(payload.group_ids) - existing_ids
        if missing:
            raise HTTPException(status_code=400, detail=f"group_ids_not_found: {sorted(missing)}")

    db.query(UserGroupMembership).filter(UserGroupMembership.user_id == user_id).delete()
    for gid in payload.group_ids:
        db.add(UserGroupMembership(user_id=user_id, group_id=gid))
    db.commit()
    return {"group_ids": payload.group_ids}


# ---------------------------------------------------------------------------
# OIDC helpers
# ---------------------------------------------------------------------------


def _get_oidc_client(db: Session) -> tuple[OAuth, str]:
    """Read OIDC config from settings table and return a configured OAuth client + provider name."""
    issuer_row = db.query(Setting).filter(Setting.key == "oidc_issuer_url").first()
    client_id_row = db.query(Setting).filter(Setting.key == "oidc_client_id").first()
    client_secret_row = db.query(Setting).filter(Setting.key == "oidc_client_secret").first()
    provider_name_row = db.query(Setting).filter(Setting.key == "oidc_provider_name").first()

    if not issuer_row or not client_id_row:
        raise HTTPException(status_code=400, detail="oidc_not_configured")

    # Client secret is optional — when absent, we use PKCE (public client flow)
    client_secret = None
    if client_secret_row and client_secret_row.value:
        try:
            client_secret = decrypt(client_secret_row.value)
        except Exception:
            raise HTTPException(status_code=500, detail="oidc_config_corrupt")

    provider_name = provider_name_row.value if provider_name_row else "oidc"
    issuer_url = issuer_row.value.rstrip("/")

    # Include groups scope if a groups_claim is configured
    groups_claim_row = db.query(Setting).filter(Setting.key == "oidc_groups_claim").first()
    groups_claim = groups_claim_row.value if groups_claim_row else "groups"
    scopes = "openid email profile"
    if groups_claim:
        scopes += " " + groups_claim

    client_kwargs: dict = {"scope": scopes}
    if not client_secret:
        # Public client: use PKCE (Authorization Code + S256 challenge)
        client_kwargs["code_challenge_method"] = "S256"
        client_kwargs["token_endpoint_auth_method"] = "none"

    try:
        oauth = OAuth()
        oauth.register(
            name="oidc",
            client_id=client_id_row.value,
            client_secret=client_secret or "",
            server_metadata_url=f"{issuer_url}/.well-known/openid-configuration",
            client_kwargs=client_kwargs,
        )
    except Exception as exc:
        logger.warning("OIDC provider discovery failed: %s", exc)
        raise HTTPException(status_code=500, detail="oidc_provider_unavailable")

    return oauth, provider_name


def _sync_user_groups(db: Session, user: User, userinfo: dict) -> None:
    """Sync a user's role and profile access based on OIDC group claims.

    Reads the groups_claim setting (default 'groups'), extracts matching OIDC group
    names from userinfo, resolves them to Lapsora Group objects, and overwrites
    the user's role and UserProfileAccess rows accordingly.
    """
    groups_claim_row = db.query(Setting).filter(Setting.key == "oidc_groups_claim").first()
    groups_claim = groups_claim_row.value if groups_claim_row else "groups"

    oidc_groups = userinfo.get(groups_claim, [])
    if not isinstance(oidc_groups, list):
        logger.warning("OIDC groups claim '%s' is not a list: %r", groups_claim, oidc_groups)
        return

    if not oidc_groups:
        return

    # Find matching Lapsora groups via OIDCGroupMapping
    mappings = (
        db.query(OIDCGroupMapping)
        .filter(OIDCGroupMapping.oidc_group_name.in_(oidc_groups))
        .all()
    )
    if not mappings:
        return

    matched_group_ids = [m.group_id for m in mappings]
    matched_groups = db.query(Group).filter(Group.id.in_(matched_group_ids)).all()

    if not matched_groups:
        return

    # Compute effective role: admin if any group is admin, else user
    effective_role = "user"
    for g in matched_groups:
        if g.role == "admin":
            effective_role = "admin"
            break

    user.role = effective_role

    # Compute effective profile access: union of all matched groups' profile IDs
    all_profile_ids: set[int] = set()
    for g in matched_groups:
        gpa_rows = db.query(GroupProfileAccess).filter(GroupProfileAccess.group_id == g.id).all()
        for row in gpa_rows:
            all_profile_ids.add(row.profile_id)

    # Replace user's profile access
    db.query(UserProfileAccess).filter(UserProfileAccess.user_id == user.id).delete()
    for pid in all_profile_ids:
        db.add(UserProfileAccess(user_id=user.id, profile_id=pid))

    db.commit()
    logger.info(
        "OIDC group sync: user_id=%d role=%s profiles=%s",
        user.id, effective_role, sorted(all_profile_ids),
    )


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
    groups_claim_row = db.query(Setting).filter(Setting.key == "oidc_groups_claim").first()

    if not issuer_row:
        return OIDCConfigRead(enabled=False)

    return OIDCConfigRead(
        enabled=True,
        provider_name=provider_name_row.value if provider_name_row else None,
        issuer_url=issuer_row.value,
        groups_claim=groups_claim_row.value if groups_claim_row else "groups",
    )


@router.put("/oidc/config", response_model=OIDCConfigRead)
def put_oidc_config(
    payload: OIDCConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Save OIDC provider config (admin-only)."""

    def _upsert(key: str, value: str) -> None:
        row = db.query(Setting).filter(Setting.key == key).first()
        if row:
            row.value = value
        else:
            db.add(Setting(key=key, value=value))

    _upsert("oidc_issuer_url", payload.issuer_url)
    _upsert("oidc_client_id", payload.client_id)

    # Client secret is optional — encrypt and store when provided, clear when empty
    if payload.client_secret:
        encrypted_secret = encrypt(payload.client_secret)
        _upsert("oidc_client_secret", encrypted_secret)
    else:
        # Clear any previously stored secret (switching to public client / PKCE)
        row = db.query(Setting).filter(Setting.key == "oidc_client_secret").first()
        if row:
            row.value = ""
    if payload.provider_name is not None:
        _upsert("oidc_provider_name", payload.provider_name)
    if payload.groups_claim is not None:
        _upsert("oidc_groups_claim", payload.groups_claim)
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

    # Sync group-based role and profile access from OIDC claims
    try:
        _sync_user_groups(db, user, userinfo)
    except Exception as exc:
        logger.warning("OIDC group sync failed (non-fatal): %s", exc)

    logger.info("OIDC login: user_id=%d provider=%s", user.id, provider_name)

    response = RedirectResponse(url="/")
    _issue_jwt_cookie(response, user)
    return response
