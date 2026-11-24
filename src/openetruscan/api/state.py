"""Process-wide mutable state shared between the app lifespan and the routers."""

from datetime import datetime, timezone

# Reset by the app lifespan at startup; /health reports uptime from it.
START_TIME = datetime.now(timezone.utc)
