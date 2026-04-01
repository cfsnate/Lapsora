"""Admin-only TLS / ACME certificate management endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.schemas import TLSAcquireRequest, TLSCertificateInfo, TLSConfigRead, TLSConfigUpdate
from app.services.tls import (
    acquire_certificate,
    get_certificate_info,
    get_tls_settings,
    update_tls_settings,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/tls",
    tags=["tls"],
    dependencies=[Depends(require_admin)],
)


@router.get("/config", response_model=TLSConfigRead)
def get_tls_config(db: Session = Depends(get_db)):
    """Return current TLS configuration from the settings table."""
    cfg = get_tls_settings(db)
    cert_info = get_certificate_info()
    return TLSConfigRead(
        domain=cfg.get("domain") or "",
        email=cfg.get("email") or "",
        acme_directory_url=cfg.get("acme_directory_url") or "",
        acme_ca_bundle=cfg.get("acme_ca_bundle") or "",
        enabled=bool(cfg.get("enabled")),
        has_certificate=cert_info is not None,
    )


@router.put("/config", response_model=TLSConfigRead)
def put_tls_config(body: TLSConfigUpdate, db: Session = Depends(get_db)):
    """Update TLS configuration in the settings table."""
    update_tls_settings(
        db,
        domain=body.domain,
        email=body.email,
        acme_directory_url=body.acme_directory_url,
        acme_ca_bundle=body.acme_ca_bundle,
        enabled=body.enabled,
    )
    cfg = get_tls_settings(db)
    cert_info = get_certificate_info()
    return TLSConfigRead(
        domain=cfg.get("domain") or "",
        email=cfg.get("email") or "",
        acme_directory_url=cfg.get("acme_directory_url") or "",
        acme_ca_bundle=cfg.get("acme_ca_bundle") or "",
        enabled=bool(cfg.get("enabled")),
        has_certificate=cert_info is not None,
    )


@router.post("/acquire")
def acquire_cert(body: TLSAcquireRequest, db: Session = Depends(get_db)):
    """Trigger ACME certificate acquisition.

    If *force* is False (default) and a certificate is already present and not
    expiring within 30 days, the call is a no-op and returns a message saying so.
    """
    from app.services.tls import check_renewal_needed

    if not body.force:
        if not check_renewal_needed():
            return {"success": True, "message": "Certificate is already valid and not due for renewal."}

    cfg = get_tls_settings(db)
    domain = cfg.get("domain") or ""
    if not domain:
        raise HTTPException(status_code=400, detail="No domain configured. Set a domain via PUT /api/tls/config first.")

    logger.info("Starting ACME certificate acquisition for domain %s (force=%s)", domain, body.force)
    ok = acquire_certificate(domain, db)
    if ok:
        return {"success": True, "message": f"Certificate successfully acquired for {domain}."}
    raise HTTPException(status_code=502, detail="Certificate acquisition failed. Check server logs for details.")


@router.get("/certificate", response_model=TLSCertificateInfo)
def get_cert():
    """Return metadata about the stored TLS certificate, or 404 if none exists."""
    info = get_certificate_info()
    if info is None:
        raise HTTPException(status_code=404, detail="No certificate found.")
    return info
