"""Health, readiness and liveness probes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from openetruscan import __version__
from openetruscan.api import state
from openetruscan.core.config import settings
from openetruscan.db.repository import InscriptionRepository
from openetruscan.db.session import get_session

router = APIRouter()


@router.get("/health", tags=["Health"])
async def health_check(request: Request, session: AsyncSession = Depends(get_session)):
    """Deep health check.

    Returns 200 with `status: healthy` only when every dependency the public
    surface actually needs is reachable. A 503 is preferable to a green check
    while the DB is gone.
    """
    uptime = (datetime.now(timezone.utc) - state.START_TIME).total_seconds()

    rss_mb = 0.0
    try:
        import resource

        rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_mb = round(rss_kb / 1024, 1)
    except ImportError:
        pass

    async def probe_db():
        try:
            t0 = datetime.now(timezone.utc)
            count = await InscriptionRepository(session).count()
            ms = (datetime.now(timezone.utc) - t0).total_seconds() * 1000
            return {"ok": count > 0, "count": count, "latency_ms": round(ms, 1)}
        except Exception as e:
            return {"ok": False, "error": type(e).__name__}

    db_result = await probe_db()

    deps_ok = db_result["ok"]
    status_code = 200 if deps_ok else 503

    body = {
        "status": "healthy" if deps_ok else "unhealthy",
        "version": __version__,
        "uptime_seconds": round(uptime, 2),
        "mem_rss_mb": rss_mb,
        "checks": {
            "db": db_result,
            "gemini_configured": bool(settings.gemini_api_key),
            "admin_token_configured": bool(settings.admin_token),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return JSONResponse(content=body, status_code=status_code)


@router.get("/ready", tags=["Health"])
async def readiness_check(session: AsyncSession = Depends(get_session)):
    """Readiness probe for Kubernetes."""
    repo = InscriptionRepository(session)
    count = await repo.count()
    if count == 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Corpus not loaded",
        )
    return {"status": "ready"}


@router.get("/live", tags=["Health"])
async def liveness_check():
    """Liveness probe for Kubernetes."""
    return {"status": "alive"}
