"""HTTP routers, one module per API domain.

To add a domain, create ``routes/<name>.py`` exposing ``router = APIRouter()``
and add the module to the mount tuple at the end of ``api/server.py``. Shared
dependencies (admin auth, rate limiter, input bounds) live in ``api/deps.py``,
shared response models in ``api/schemas.py``.
"""
