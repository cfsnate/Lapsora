"""ACME / TLS certificate management service.

Handles:
- ACME account key generation & encrypted storage (settings table)
- ACME account registration via ClientV2
- HTTP-01 challenge token provisioning (module-level dict, served by router)
- Certificate order creation, finalization, and PEM file writing
- Certificate info parsing (expiry, issuer, domain)
- Renewal detection (< 30 days) and renewal trigger
- Helpers for persisting TLS configuration in the settings table
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

import josepy as jose
from acme import challenges, client, messages
from acme.crypto_util import make_csr
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.config import decrypt, encrypt, settings as app_settings
from app.models import Setting
from app.schemas import TLSCertificateInfo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level HTTP-01 challenge token store
# { token_str: key_authorisation_str }
# ---------------------------------------------------------------------------
_challenge_tokens: dict[str, str] = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SETTING_KEY_ACCOUNT_KEY = "tls_acme_account_key"
SETTING_KEY_ACCOUNT_URI = "tls_acme_account_uri"
SETTING_KEY_TLS_DOMAIN = "tls_domain"
SETTING_KEY_TLS_EMAIL = "tls_acme_email"
SETTING_KEY_ACME_DIRECTORY = "tls_acme_directory_url"
SETTING_KEY_ACME_CA_BUNDLE = "tls_acme_ca_bundle"
SETTING_KEY_TLS_ENABLED = "tls_enabled"


def _get_cert_dir() -> Path:
    """Return the certs directory, creating it if necessary."""
    if app_settings.TLS_CERT_DIR:
        cert_dir = Path(app_settings.TLS_CERT_DIR)
    else:
        cert_dir = Path(app_settings.DATA_DIR) / "certs"
    cert_dir.mkdir(parents=True, exist_ok=True)
    return cert_dir


def _db_get(db, key: str) -> Optional[str]:
    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row else None


def _db_set(db, key: str, value: str) -> None:
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
    db.commit()


# ---------------------------------------------------------------------------
# Account key
# ---------------------------------------------------------------------------

def _get_account_key(db) -> rsa.RSAPrivateKey:
    """Load the RSA account key from the encrypted settings row, or generate+store one."""
    encrypted = _db_get(db, SETTING_KEY_ACCOUNT_KEY)
    if encrypted:
        try:
            pem_bytes = decrypt(encrypted).encode()
            key = serialization.load_pem_private_key(pem_bytes, password=None)
            if isinstance(key, rsa.RSAPrivateKey):
                return key
        except Exception:
            logger.warning("Failed to load stored ACME account key; generating new one")

    # Generate a new 2048-bit RSA key
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    pem_str = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    _db_set(db, SETTING_KEY_ACCOUNT_KEY, encrypt(pem_str))
    logger.info("Generated new ACME account key")
    return key


# ---------------------------------------------------------------------------
# ACME client
# ---------------------------------------------------------------------------

def _get_acme_client(db) -> client.ClientV2:
    """Build and return an authenticated ACME ClientV2.

    Registers a new account if one doesn't exist yet, otherwise reuses the
    stored account URI so the server recognises us immediately.
    """
    account_key = _get_account_key(db)
    jose_key = jose.JWKRSA(key=account_key)

    directory_url = _db_get(db, SETTING_KEY_ACME_DIRECTORY) or app_settings.ACME_DIRECTORY_URL
    email = _db_get(db, SETTING_KEY_TLS_EMAIL) or app_settings.ACME_EMAIL
    ca_bundle = _db_get(db, SETTING_KEY_ACME_CA_BUNDLE) or app_settings.ACME_CA_BUNDLE

    # verify_ssl accepts True (system trust store) or a path to a CA bundle PEM.
    # This allows connecting to internal ACME servers with private/self-signed CAs.
    verify_ssl: bool | str = ca_bundle if ca_bundle else True

    net = client.ClientNetwork(key=jose_key, user_agent="lapsora-acme/1.0", verify_ssl=verify_ssl)
    directory = client.ClientV2.get_directory(directory_url, net)
    acme_client = client.ClientV2(directory, net)

    # Re-use existing account URI if available
    stored_uri = _db_get(db, SETTING_KEY_ACCOUNT_URI)
    if stored_uri:
        try:
            existing_regr = messages.RegistrationResource(uri=stored_uri, body=messages.Registration())
            acme_client.net.account = acme_client.query_registration(existing_regr)
            logger.debug("Reusing ACME account %s", stored_uri)
            return acme_client
        except Exception:
            logger.warning("Stored ACME account URI invalid; re-registering")

    # Register new account
    contact = (f"mailto:{email}",) if email else ()
    new_reg = messages.NewRegistration.from_data(
        email=email if email else None,
        terms_of_service_agreed=True,
    )
    regr = acme_client.new_account(new_reg)
    acme_client.net.account = regr
    _db_set(db, SETTING_KEY_ACCOUNT_URI, regr.uri)
    logger.info("Registered new ACME account: %s", regr.uri)
    return acme_client


# ---------------------------------------------------------------------------
# Challenge token management
# ---------------------------------------------------------------------------

def get_challenge_response(token: str) -> Optional[str]:
    """Return the key-authorisation string for the given token, or None."""
    return _challenge_tokens.get(token)


def _store_challenge(token: str, key_auth: str) -> None:
    _challenge_tokens[token] = key_auth
    logger.debug("Stored HTTP-01 challenge token %s", token)


def _remove_challenge(token: str) -> None:
    _challenge_tokens.pop(token, None)
    logger.debug("Removed HTTP-01 challenge token %s", token)


# ---------------------------------------------------------------------------
# Certificate acquisition
# ---------------------------------------------------------------------------

def _generate_domain_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )


def acquire_certificate(domain: str, db) -> bool:
    """Run the full ACME HTTP-01 challenge flow and write cert files to cert_dir.

    Writes:
      <cert_dir>/fullchain.pem   — certificate + intermediates
      <cert_dir>/privkey.pem     — domain private key

    Returns True on success, False on failure.
    """
    cert_dir = _get_cert_dir()

    logger.info("ACME step 1/5: Building ACME client...")
    try:
        acme_client = _get_acme_client(db)
    except Exception:
        logger.exception("Failed to build ACME client")
        return False

    # Generate a fresh domain key and CSR
    logger.info("ACME step 2/5: Generating domain key and CSR for %s", domain)
    domain_key = _generate_domain_key()
    domain_key_pem = domain_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    csr_pem = make_csr(domain_key_pem, domains=[domain])

    logger.info("ACME step 3/5: Creating order...")
    try:
        order = acme_client.new_order(csr_pem)
    except Exception:
        logger.exception("Failed to create ACME order for domain %s", domain)
        return False

    # Respond to HTTP-01 challenges
    logger.info("ACME step 4/5: Answering HTTP-01 challenges...")
    token_values: list[str] = []
    for authz in order.authorizations:
        for challb in authz.body.challenges:
            if isinstance(challb.chall, challenges.HTTP01):
                token = challb.chall.encode("token")
                key_auth = challb.chall.key_authorization(acme_client.net.key)
                _store_challenge(token, key_auth)
                token_values.append(token)
                logger.info(
                    "ACME challenge ready: token=%s — verify the ACME server can reach "
                    "http://%s/.well-known/acme-challenge/%s",
                    token[:16] + "...", domain, token[:16] + "...",
                )
                try:
                    acme_client.answer_challenge(challb, challb.chall.response(acme_client.net.key))
                except Exception:
                    logger.exception("Failed to answer challenge for token %s", token)
                    for t in token_values:
                        _remove_challenge(t)
                    return False

    # Poll and finalize
    # acme-python's poll_authorizations compares deadline against datetime.now()
    # (naive), so the deadline must also be naive to avoid a TypeError.
    logger.info("ACME step 5/5: Polling for authorization and finalizing (timeout: 90s)...")
    deadline = datetime.utcnow() + timedelta(seconds=90)
    try:
        order = acme_client.poll_and_finalize(order, deadline=deadline)
    except Exception:
        logger.exception(
            "ACME order finalization failed for %s. This usually means the ACME server "
            "could not reach http://%s/.well-known/acme-challenge/<token> on port 80. "
            "Check that port 80 is forwarded to this application and not blocked by a firewall.",
            domain, domain,
        )
        for t in token_values:
            _remove_challenge(t)
        return False
    finally:
        for t in token_values:
            _remove_challenge(t)

    # Write cert files
    fullchain_path = cert_dir / "fullchain.pem"
    privkey_path = cert_dir / "privkey.pem"

    fullchain_pem = order.fullchain_pem
    if isinstance(fullchain_pem, str):
        fullchain_pem = fullchain_pem.encode()

    fullchain_path.write_bytes(fullchain_pem)
    privkey_path.write_bytes(domain_key_pem)
    privkey_path.chmod(0o600)

    logger.info("Certificate acquired for %s, written to %s", domain, cert_dir)
    return True


# ---------------------------------------------------------------------------
# Certificate introspection
# ---------------------------------------------------------------------------

def get_certificate_info() -> Optional[TLSCertificateInfo]:
    """Parse the stored fullchain.pem and return certificate metadata."""
    cert_dir = _get_cert_dir()
    fullchain_path = cert_dir / "fullchain.pem"
    if not fullchain_path.exists():
        return None

    try:
        cert_pem = fullchain_path.read_bytes()
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
    except Exception:
        logger.exception("Failed to parse certificate at %s", fullchain_path)
        return None

    try:
        cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        domain = cn[0].value if cn else ""
    except Exception:
        domain = ""

    # Many modern CAs (e.g. Smallstep) leave CN empty and put the domain
    # only in Subject Alternative Names. Fall back to the first SAN DNS entry.
    if not domain:
        try:
            san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            dns_names = san_ext.value.get_values_for_type(x509.DNSName)
            if dns_names:
                domain = dns_names[0]
        except (x509.ExtensionNotFound, Exception):
            pass

    try:
        issuer_cn = cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)
        issuer = issuer_cn[0].value if issuer_cn else str(cert.issuer)
    except Exception:
        issuer = str(cert.issuer)

    not_before: datetime = cert.not_valid_before_utc
    not_after: datetime = cert.not_valid_after_utc
    now = datetime.now(UTC)
    is_expired = now > not_after
    days_until_expiry = (not_after - now).days

    serial_number = format(cert.serial_number, "x")

    return TLSCertificateInfo(
        domain=domain,
        issuer=issuer,
        not_before=not_before,
        not_after=not_after,
        serial_number=serial_number,
        is_expired=is_expired,
        days_until_expiry=days_until_expiry,
    )


# ---------------------------------------------------------------------------
# Renewal logic
# ---------------------------------------------------------------------------

RENEWAL_THRESHOLD_DAYS = 30


def check_renewal_needed() -> bool:
    """Return True if the certificate is missing, expired, or expires in < 30 days."""
    info = get_certificate_info()
    if info is None:
        return True
    return info.days_until_expiry < RENEWAL_THRESHOLD_DAYS


def renew_certificate(db) -> bool:
    """Renew the certificate if needed, using the stored domain setting."""
    domain = _db_get(db, SETTING_KEY_TLS_DOMAIN) or app_settings.TLS_DOMAIN
    if not domain:
        logger.error("Cannot renew certificate: no domain configured")
        return False
    logger.info("Renewing certificate for domain %s", domain)
    return acquire_certificate(domain, db)


# ---------------------------------------------------------------------------
# TLS settings helpers
# ---------------------------------------------------------------------------

def get_tls_settings(db) -> dict:
    """Return a dict of current TLS settings from the settings table + config fallbacks."""
    return {
        "domain": _db_get(db, SETTING_KEY_TLS_DOMAIN) or app_settings.TLS_DOMAIN,
        "email": _db_get(db, SETTING_KEY_TLS_EMAIL) or app_settings.ACME_EMAIL,
        "acme_directory_url": _db_get(db, SETTING_KEY_ACME_DIRECTORY) or app_settings.ACME_DIRECTORY_URL,
        "acme_ca_bundle": _db_get(db, SETTING_KEY_ACME_CA_BUNDLE) or app_settings.ACME_CA_BUNDLE,
        "enabled": (_db_get(db, SETTING_KEY_TLS_ENABLED) or str(app_settings.TLS_ENABLED)).lower() == "true",
    }


def update_tls_settings(db, *, domain: Optional[str] = None, email: Optional[str] = None,
                         acme_directory_url: Optional[str] = None, acme_ca_bundle: Optional[str] = None,
                         enabled: Optional[bool] = None) -> None:
    """Persist TLS settings to the settings table."""
    if domain is not None:
        _db_set(db, SETTING_KEY_TLS_DOMAIN, domain)
    if email is not None:
        _db_set(db, SETTING_KEY_TLS_EMAIL, email)
    if acme_directory_url is not None:
        _db_set(db, SETTING_KEY_ACME_DIRECTORY, acme_directory_url)
    if acme_ca_bundle is not None:
        _db_set(db, SETTING_KEY_ACME_CA_BUNDLE, acme_ca_bundle)
    if enabled is not None:
        _db_set(db, SETTING_KEY_TLS_ENABLED, str(enabled).lower())


# ---------------------------------------------------------------------------
# Hot-start HTTPS listener (no container restart required)
# ---------------------------------------------------------------------------

_https_server = None  # Track the running HTTPS server so we don't start duplicates


def start_https_listener() -> bool:
    """Start a uvicorn HTTPS server on port 443 in a background thread.

    Called after certificate acquisition so TLS activates immediately
    without a container restart.  Returns True if started, False if
    certs are missing or a listener is already running.
    """
    global _https_server  # noqa: PLW0603

    if _https_server is not None:
        logger.info("HTTPS listener already running on port 443")
        return False

    cert_dir = _get_cert_dir()
    fullchain = cert_dir / "fullchain.pem"
    privkey = cert_dir / "privkey.pem"
    if not fullchain.exists() or not privkey.exists():
        logger.warning("Cannot start HTTPS listener: cert files missing")
        return False

    import threading
    import uvicorn

    config = uvicorn.Config(
        "app.main:app",
        host="0.0.0.0",
        port=443,
        ssl_certfile=str(fullchain),
        ssl_keyfile=str(privkey),
        log_level="info",
    )
    server = uvicorn.Server(config)
    _https_server = server

    thread = threading.Thread(target=server.run, name="https-listener", daemon=True)
    thread.start()
    logger.info("HTTPS listener started on port 443 (hot-start, no restart needed)")
    return True
