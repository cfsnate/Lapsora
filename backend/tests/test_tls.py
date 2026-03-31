"""Comprehensive tests for the TLS / ACME service, API endpoints,
challenge route, redirect middleware, and certificate utilities."""

from __future__ import annotations

import ipaddress
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SETUP_URL = "/api/auth/setup"
LOGIN_URL = "/api/auth/login"
LOGOUT_URL = "/api/auth/logout"
CONFIG_URL = "/api/tls/config"
ACQUIRE_URL = "/api/tls/acquire"
CERT_URL = "/api/tls/certificate"
CHALLENGE_BASE = "/.well-known/acme-challenge"

ADMIN_PAYLOAD = {
    "username": "admin",
    "display_name": "Admin",
    "password": "adminpass1",
    "email": "admin@example.com",
}
ADMIN_CREDS = {"username": "admin", "password": "adminpass1"}

USER_PAYLOAD = {
    "username": "regular",
    "display_name": "Regular",
    "password": "userpass1",
}
USER_CREDS = {"username": "regular", "password": "userpass1"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _admin_login(client: TestClient) -> None:
    """Set up admin account and log in."""
    client.post(SETUP_URL, json=ADMIN_PAYLOAD)
    resp = client.post(LOGIN_URL, json=ADMIN_CREDS)
    assert resp.status_code == 200


def _make_self_signed_cert(
    domain: str = "example.com",
    days_valid: int = 90,
    days_offset: int = 0,
) -> tuple[bytes, bytes]:
    """Generate a self-signed cert (PEM) and its private key (PEM).

    *days_offset* shifts both not_before and not_after by that many days
    relative to now — useful for creating already-expired certs.
    """
    key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    now = datetime.now(UTC)
    not_before = now + timedelta(days=days_offset)
    not_after = not_before + timedelta(days=days_valid)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, domain),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test Org"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(domain)]),
            critical=False,
        )
        .sign(key, hashes.SHA256(), default_backend())
    )

    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    return cert_pem, key_pem


# ---------------------------------------------------------------------------
# TLS config GET
# ---------------------------------------------------------------------------


def test_tls_config_get_requires_admin_unauthenticated(client: TestClient):
    """GET /api/tls/config without auth returns 401."""
    resp = client.get(CONFIG_URL)
    assert resp.status_code == 401


def test_tls_config_get_requires_admin_non_admin(client: TestClient):
    """GET /api/tls/config as non-admin returns 403."""
    _admin_login(client)
    # Create a non-admin user via admin session
    client.post(
        "/api/auth/users",
        json={**USER_PAYLOAD, "email": None, "role": "user"},
    )
    client.post(LOGOUT_URL)
    resp_login = client.post(LOGIN_URL, json=USER_CREDS)
    assert resp_login.status_code == 200
    resp = client.get(CONFIG_URL)
    assert resp.status_code == 403


def test_tls_config_get_returns_schema(client: TestClient):
    """GET /api/tls/config as admin returns TLSConfigRead schema."""
    _admin_login(client)
    resp = client.get(CONFIG_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert "domain" in data
    assert "email" in data
    assert "acme_directory_url" in data
    assert "enabled" in data
    assert "has_certificate" in data
    assert isinstance(data["enabled"], bool)
    assert isinstance(data["has_certificate"], bool)


def test_tls_config_get_has_certificate_false_when_no_cert(client: TestClient):
    """has_certificate is False when no cert file exists."""
    _admin_login(client)
    with patch("app.routers.tls.get_certificate_info", return_value=None):
        resp = client.get(CONFIG_URL)
    assert resp.status_code == 200
    assert resp.json()["has_certificate"] is False


# ---------------------------------------------------------------------------
# TLS config PUT
# ---------------------------------------------------------------------------


def test_tls_config_put_requires_admin(client: TestClient):
    """PUT /api/tls/config without auth returns 401."""
    resp = client.put(CONFIG_URL, json={"domain": "example.com"})
    assert resp.status_code == 401


def test_tls_config_put_updates_domain(client: TestClient):
    """PUT /api/tls/config updates domain and reflects in GET response."""
    _admin_login(client)
    resp = client.put(CONFIG_URL, json={"domain": "new.example.com", "email": "cert@example.com"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["domain"] == "new.example.com"
    assert data["email"] == "cert@example.com"


def test_tls_config_put_partial_update(client: TestClient):
    """PUT with only one field only changes that field."""
    _admin_login(client)
    client.put(CONFIG_URL, json={"domain": "first.example.com", "email": "first@example.com"})
    resp = client.put(CONFIG_URL, json={"email": "second@example.com"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "second@example.com"
    # domain should still be first.example.com (not reset to empty)
    assert data["domain"] == "first.example.com"


def test_tls_config_put_enabled_flag(client: TestClient):
    """PUT can toggle enabled flag."""
    _admin_login(client)
    resp = client.put(CONFIG_URL, json={"enabled": True})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True

    resp2 = client.put(CONFIG_URL, json={"enabled": False})
    assert resp2.status_code == 200
    assert resp2.json()["enabled"] is False


# ---------------------------------------------------------------------------
# Acquire endpoint
# ---------------------------------------------------------------------------


def test_acquire_requires_admin(client: TestClient):
    """POST /api/tls/acquire without auth returns 401."""
    resp = client.post(ACQUIRE_URL, json={"force": False})
    assert resp.status_code == 401


def test_acquire_returns_400_when_domain_not_configured(client: TestClient):
    """Acquire without a domain configured returns HTTP 400."""
    _admin_login(client)
    # Ensure no domain is set and cert needs renewal
    with patch("app.services.tls.check_renewal_needed", return_value=True):
        resp = client.post(ACQUIRE_URL, json={"force": True})
    assert resp.status_code == 400
    assert "domain" in resp.json()["detail"].lower()


def test_acquire_skips_when_cert_valid_and_not_forced(client: TestClient):
    """Acquire returns success without touching ACME when cert is valid."""
    _admin_login(client)
    with patch("app.services.tls.check_renewal_needed", return_value=False):
        resp = client.post(ACQUIRE_URL, json={"force": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "renewal" in data["message"].lower() or "valid" in data["message"].lower()


def test_acquire_calls_acme_when_renewal_needed(client: TestClient):
    """Acquire triggers ACME acquisition when renewal is needed."""
    _admin_login(client)
    client.put(CONFIG_URL, json={"domain": "acme.example.com"})
    # acquire_certificate is imported at module-level in the router, so patch
    # it where it is looked up (app.routers.tls), not in app.services.tls.
    with (
        patch("app.services.tls.check_renewal_needed", return_value=True),
        patch("app.routers.tls.acquire_certificate", return_value=True) as mock_acq,
    ):
        resp = client.post(ACQUIRE_URL, json={"force": False})
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    mock_acq.assert_called_once()


def test_acquire_returns_502_on_acme_failure(client: TestClient):
    """Acquire returns 502 when ACME acquisition fails."""
    _admin_login(client)
    client.put(CONFIG_URL, json={"domain": "fail.example.com"})
    with (
        patch("app.services.tls.check_renewal_needed", return_value=True),
        patch("app.routers.tls.acquire_certificate", return_value=False),
    ):
        resp = client.post(ACQUIRE_URL, json={"force": True})
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# Certificate info endpoint
# ---------------------------------------------------------------------------


def test_cert_endpoint_404_when_no_cert(client: TestClient):
    """GET /api/tls/certificate returns 404 when no certificate exists."""
    _admin_login(client)
    with patch("app.routers.tls.get_certificate_info", return_value=None):
        resp = client.get(CERT_URL)
    assert resp.status_code == 404


def test_cert_endpoint_returns_cert_info(client: TestClient):
    """GET /api/tls/certificate returns TLSCertificateInfo schema when cert exists."""
    _admin_login(client)
    from app.schemas import TLSCertificateInfo
    fake_info = TLSCertificateInfo(
        domain="test.example.com",
        issuer="Test CA",
        not_before=datetime.now(UTC),
        not_after=datetime.now(UTC) + timedelta(days=80),
        serial_number="abcdef01",
        is_expired=False,
        days_until_expiry=80,
    )
    # get_certificate_info is imported by-name in the router; patch there.
    with patch("app.routers.tls.get_certificate_info", return_value=fake_info):
        resp = client.get(CERT_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert data["domain"] == "test.example.com"
    assert data["issuer"] == "Test CA"
    assert data["is_expired"] is False


# ---------------------------------------------------------------------------
# ACME challenge route
# ---------------------------------------------------------------------------


def test_challenge_returns_404_for_unknown_token(client: TestClient):
    """GET /.well-known/acme-challenge/<unknown> → 404."""
    resp = client.get(f"{CHALLENGE_BASE}/unknown-token-xyz")
    assert resp.status_code == 404


def test_challenge_returns_key_auth_for_known_token(client: TestClient):
    """Challenge route returns the key authorisation string for a stored token."""
    from app.services.tls import _challenge_tokens
    token = "test-challenge-token-abc"
    key_auth = "test-challenge-token-abc.key_authorisation_value_here"
    _challenge_tokens[token] = key_auth
    try:
        resp = client.get(f"{CHALLENGE_BASE}/{token}")
        assert resp.status_code == 200
        assert resp.text == key_auth
    finally:
        _challenge_tokens.pop(token, None)


def test_challenge_returns_plain_text_content_type(client: TestClient):
    """Challenge response must have text/plain content-type (ACME requirement)."""
    from app.services.tls import _challenge_tokens
    token = "ct-test-token"
    _challenge_tokens[token] = f"{token}.keyauth"
    try:
        resp = client.get(f"{CHALLENGE_BASE}/{token}")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers.get("content-type", "")
    finally:
        _challenge_tokens.pop(token, None)


# ---------------------------------------------------------------------------
# HTTPS redirect middleware
# ---------------------------------------------------------------------------


def test_redirect_middleware_inactive_when_tls_disabled(client: TestClient):
    """No redirect when TLS_ENABLED is False."""
    from app.config import settings as app_settings
    original = app_settings.TLS_ENABLED
    try:
        app_settings.TLS_ENABLED = False
        resp = client.get("/api/auth/setup-status")
        # Should NOT be a redirect — endpoint serves normally
        assert resp.status_code != 301
        assert resp.status_code != 302
    finally:
        app_settings.TLS_ENABLED = original


def test_redirect_middleware_redirects_http_when_tls_enabled(client: TestClient):
    """Middleware issues 301 redirect for plain HTTP requests when TLS_ENABLED."""
    from app.config import settings as app_settings
    original = app_settings.TLS_ENABLED
    try:
        app_settings.TLS_ENABLED = True
        # TestClient follows redirects by default — use allow_redirects=False
        resp = client.get(
            "/api/auth/setup-status",
            headers={"x-forwarded-proto": "http"},
            follow_redirects=False,
        )
        assert resp.status_code == 301
        assert resp.headers["location"].startswith("https://")
    finally:
        app_settings.TLS_ENABLED = original


def test_redirect_middleware_skips_already_https(client: TestClient):
    """No redirect when X-Forwarded-Proto is https."""
    from app.config import settings as app_settings
    original = app_settings.TLS_ENABLED
    try:
        app_settings.TLS_ENABLED = True
        resp = client.get(
            "/api/auth/setup-status",
            headers={"x-forwarded-proto": "https"},
        )
        assert resp.status_code != 301
        assert resp.status_code != 302
    finally:
        app_settings.TLS_ENABLED = original


def test_redirect_middleware_skips_acme_challenge_path(client: TestClient):
    """Middleware must pass ACME challenge paths through even when TLS enabled."""
    from app.config import settings as app_settings
    original = app_settings.TLS_ENABLED
    try:
        app_settings.TLS_ENABLED = True
        # A 404 (token not found) means the request went through, not a redirect
        resp = client.get(
            f"{CHALLENGE_BASE}/some-token",
            headers={"x-forwarded-proto": "http"},
            follow_redirects=False,
        )
        # Should not be a redirect — ACME challenge must be reachable over HTTP
        assert resp.status_code != 301
        assert resp.status_code != 302
    finally:
        app_settings.TLS_ENABLED = original


# ---------------------------------------------------------------------------
# get_certificate_info — unit tests with real self-signed cert
# ---------------------------------------------------------------------------


def test_get_certificate_info_returns_none_when_no_file():
    """get_certificate_info returns None when fullchain.pem doesn't exist."""
    from app.services.tls import get_certificate_info
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("app.services.tls._get_cert_dir", return_value=Path(tmpdir)):
            result = get_certificate_info()
    assert result is None


def test_get_certificate_info_parses_self_signed_cert():
    """get_certificate_info correctly parses a real self-signed certificate."""
    from app.services.tls import get_certificate_info

    cert_pem, _ = _make_self_signed_cert(domain="parse.example.com", days_valid=90)

    with tempfile.TemporaryDirectory() as tmpdir:
        fullchain = Path(tmpdir) / "fullchain.pem"
        fullchain.write_bytes(cert_pem)

        with patch("app.services.tls._get_cert_dir", return_value=Path(tmpdir)):
            info = get_certificate_info()

    assert info is not None
    assert info.domain == "parse.example.com"
    assert info.is_expired is False
    assert info.days_until_expiry >= 88  # ~90 days minus test execution time


def test_get_certificate_info_expired_cert():
    """get_certificate_info correctly identifies an expired certificate."""
    from app.services.tls import get_certificate_info

    # Cert valid 180 days starting 200 days ago → expired 20 days ago
    cert_pem, _ = _make_self_signed_cert(
        domain="expired.example.com", days_valid=180, days_offset=-200
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        fullchain = Path(tmpdir) / "fullchain.pem"
        fullchain.write_bytes(cert_pem)

        with patch("app.services.tls._get_cert_dir", return_value=Path(tmpdir)):
            info = get_certificate_info()

    assert info is not None
    assert info.is_expired is True
    assert info.days_until_expiry < 0


def test_get_certificate_info_returns_serial_number():
    """Certificate info includes a non-empty hex serial number."""
    from app.services.tls import get_certificate_info

    cert_pem, _ = _make_self_signed_cert(domain="serial.example.com")

    with tempfile.TemporaryDirectory() as tmpdir:
        fullchain = Path(tmpdir) / "fullchain.pem"
        fullchain.write_bytes(cert_pem)

        with patch("app.services.tls._get_cert_dir", return_value=Path(tmpdir)):
            info = get_certificate_info()

    assert info is not None
    assert len(info.serial_number) > 0
    # Serial number should be valid hex
    int(info.serial_number, 16)


# ---------------------------------------------------------------------------
# check_renewal_needed — unit tests
# ---------------------------------------------------------------------------


def test_check_renewal_needed_true_when_no_cert():
    """check_renewal_needed returns True when get_certificate_info returns None."""
    from app.services.tls import check_renewal_needed
    with patch("app.services.tls.get_certificate_info", return_value=None):
        assert check_renewal_needed() is True


def test_check_renewal_needed_true_when_expires_soon():
    """check_renewal_needed returns True when cert expires in < 30 days."""
    from app.services.tls import check_renewal_needed
    from app.schemas import TLSCertificateInfo

    expiring_soon = TLSCertificateInfo(
        domain="soon.example.com",
        issuer="Test CA",
        not_before=datetime.now(UTC) - timedelta(days=60),
        not_after=datetime.now(UTC) + timedelta(days=15),
        serial_number="aabbcc",
        is_expired=False,
        days_until_expiry=15,
    )
    with patch("app.services.tls.get_certificate_info", return_value=expiring_soon):
        assert check_renewal_needed() is True


def test_check_renewal_needed_false_when_cert_valid():
    """check_renewal_needed returns False when cert has > 30 days remaining."""
    from app.services.tls import check_renewal_needed
    from app.schemas import TLSCertificateInfo

    valid_cert = TLSCertificateInfo(
        domain="valid.example.com",
        issuer="Test CA",
        not_before=datetime.now(UTC) - timedelta(days=30),
        not_after=datetime.now(UTC) + timedelta(days=60),
        serial_number="112233",
        is_expired=False,
        days_until_expiry=60,
    )
    with patch("app.services.tls.get_certificate_info", return_value=valid_cert):
        assert check_renewal_needed() is False


def test_check_renewal_needed_true_when_expired():
    """check_renewal_needed returns True when cert is expired."""
    from app.services.tls import check_renewal_needed
    from app.schemas import TLSCertificateInfo

    expired = TLSCertificateInfo(
        domain="expired.example.com",
        issuer="Test CA",
        not_before=datetime.now(UTC) - timedelta(days=180),
        not_after=datetime.now(UTC) - timedelta(days=10),
        serial_number="ffeedd",
        is_expired=True,
        days_until_expiry=-10,
    )
    with patch("app.services.tls.get_certificate_info", return_value=expired):
        assert check_renewal_needed() is True


# ---------------------------------------------------------------------------
# Admin-only enforcement on all TLS endpoints
# ---------------------------------------------------------------------------


def test_tls_all_endpoints_require_auth(client: TestClient):
    """All TLS API endpoints return 401 when called without authentication."""
    endpoints = [
        ("GET", CONFIG_URL),
        ("PUT", CONFIG_URL),
        ("POST", ACQUIRE_URL),
        ("GET", CERT_URL),
    ]
    for method, url in endpoints:
        resp = client.request(method, url, json={})
        assert resp.status_code == 401, (
            f"{method} {url} expected 401, got {resp.status_code}"
        )


def test_tls_endpoints_return_403_for_non_admin(client: TestClient):
    """TLS API endpoints return 403 for authenticated non-admin users."""
    _admin_login(client)
    client.post(
        "/api/auth/users",
        json={**USER_PAYLOAD, "email": None, "role": "user"},
    )
    client.post(LOGOUT_URL)
    client.post(LOGIN_URL, json=USER_CREDS)

    endpoints = [
        ("GET", CONFIG_URL),
        ("PUT", CONFIG_URL),
        ("POST", ACQUIRE_URL),
        ("GET", CERT_URL),
    ]
    for method, url in endpoints:
        resp = client.request(method, url, json={})
        assert resp.status_code == 403, (
            f"{method} {url} expected 403, got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# Challenge token management — service unit tests
# ---------------------------------------------------------------------------


def test_get_challenge_response_returns_none_for_missing_token():
    """get_challenge_response returns None for tokens not in the store."""
    from app.services.tls import get_challenge_response
    assert get_challenge_response("no-such-token") is None


def test_store_and_retrieve_challenge_token():
    """_store_challenge and get_challenge_response round-trip correctly."""
    from app.services.tls import _challenge_tokens, _store_challenge, get_challenge_response
    token = "unit-test-token-xyz"
    key_auth = f"{token}.some_key_auth"
    _store_challenge(token, key_auth)
    try:
        assert get_challenge_response(token) == key_auth
    finally:
        _challenge_tokens.pop(token, None)


def test_remove_challenge_token():
    """_remove_challenge removes the token from the store."""
    from app.services.tls import _challenge_tokens, _remove_challenge, _store_challenge, get_challenge_response
    token = "remove-test-token"
    _store_challenge(token, f"{token}.auth")
    _remove_challenge(token)
    assert get_challenge_response(token) is None
