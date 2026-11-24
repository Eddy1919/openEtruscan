"""Shared request dependencies: admin auth, the rate limiter, and input bounds."""

import secrets

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from slowapi import Limiter
from slowapi.util import get_remote_address

from openetruscan.core.config import settings

security_scheme = HTTPBearer()


def verify_admin(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)):
    """Verifies that mutational operations are using the core ADMIN_TOKEN.

    If ``settings.admin_token`` is not configured this returns 503 (not 500):
    "the admin write surface is intentionally disabled" is an operational
    state, not a server bug. /health surfaces the same condition under
    ``checks.admin_token_configured`` so the gap is visible before someone
    tries to call an admin endpoint.
    """
    if not settings.admin_token:
        raise HTTPException(
            status_code=503,
            detail=(
                "Admin write endpoints are disabled because ADMIN_TOKEN is not "
                "configured on this deployment. See docs/internal/SECRETS.md."
            ),
        )
    if not secrets.compare_digest(credentials.credentials, settings.admin_token):
        raise HTTPException(status_code=403, detail="Invalid or missing admin credentials")
    return credentials


# ── Rate Limiter ────────────────────────────────────────────────────────────
def _get_rate_limit_key(request: Request) -> str:
    """Get rate limit key with path awareness."""
    client = get_remote_address(request)
    return f"{client}:{request.url.path}"


limiter = Limiter(
    key_func=_get_rate_limit_key,
    default_limits=[f"{settings.rate_limit_per_minute}/minute"],
    strategy="fixed-window",
)


# ── Input Bounds ───────────────────────────────────────────────────────────
MAX_LIMIT = 500
MAX_RADIUS_KM = 500
MAX_TEXT_LEN = 200
MAX_GENS_LEN = 100


# ── Validators ─────────────────────────────────────────────────────────────
def _clamp_limit(limit: int) -> int:
    """Clamp the pagination limit to prevent excessive resource consumption."""
    return max(1, min(limit, MAX_LIMIT))


def _clamp_text(text: str | None) -> str | None:
    """Truncate input text to the maximum supported length for safety."""
    return text[:MAX_TEXT_LEN] if text else text
