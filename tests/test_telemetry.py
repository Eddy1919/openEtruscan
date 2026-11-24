"""Request tracing skips the probe endpoints.

FastAPI >= 0.142 creates request spans natively once the app's lifespan has
installed a real tracer provider. Probes hit /health, /ready and /live every
few seconds, so the app passes an ``exclude`` hook; without it each probe
would export a span.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("opentelemetry.sdk", reason="the [telemetry] extra is not installed")
pytest.importorskip("opentelemetry.instrumentation.fastapi")

from openetruscan.api.server import _untraced  # noqa: E402


@pytest.mark.parametrize("path", ["/health", "/ready", "/live"])
def test_probe_paths_are_excluded(path):
    assert _untraced({"type": "http", "path": path})


def test_other_paths_are_traced():
    assert not _untraced({"type": "http", "path": "/inscription/1"})
    assert not _untraced({"type": "http", "path": "/healthz"})


# Entering the lifespan sets a process-wide tracer provider (settable once) and
# global asyncpg/httpx instrumentation, so the live check runs in a subprocess
# and leaves the test session's OpenTelemetry state untouched.
_PROBE = textwrap.dedent(
    """
    import json, os
    os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
    from fastapi.testclient import TestClient
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from openetruscan.api.server import app

    exporter = InMemorySpanExporter()
    spans = {}
    # The probes may 500 without a seeded database; spans don't depend on the status.
    with TestClient(app, raise_server_exceptions=False) as client:
        provider = trace.get_tracer_provider()
        if not isinstance(provider, TracerProvider):
            print(json.dumps(None))
            raise SystemExit(0)
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        for path in ("/health", "/ready", "/live", "/no-such-route"):
            exporter.clear()
            client.get(path)
            spans[path] = [s.name for s in exporter.get_finished_spans()]
    print(json.dumps(spans))
    """
)


def test_probe_requests_emit_no_request_spans():
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE], capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    spans = json.loads(proc.stdout.strip().splitlines()[-1])
    if spans is None:
        pytest.skip("lifespan did not install an SDK tracer provider")
    for path in ("/health", "/ready", "/live"):
        assert spans[path] == [], path
    assert spans["/no-such-route"], "an ordinary request should be traced"
