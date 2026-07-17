"""Startup/env-contract tests for the byt5-restorer service.

Import-time behaviour only — no model is downloaded or loaded (torch and
transformers are lazy imports inside the handlers). Not collected by the
root ``pytest`` run (``testpaths = ["tests"]``); run explicitly:

    .venv/bin/pytest services/byt5-restorer/ -q
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

SERVICE_DIR = Path(__file__).resolve().parent


@pytest.fixture
def import_main(monkeypatch, tmp_path):
    """Import services/byt5-restorer/main.py fresh, with a controlled env.

    The MODEL_URI check runs at module import, so each test needs a clean
    import under its own environment.
    """
    monkeypatch.syspath_prepend(str(SERVICE_DIR))
    monkeypatch.setenv("CACHE_PATH", str(tmp_path / "cache.db"))
    monkeypatch.delenv("MODEL_URI", raising=False)

    def _import(**env: str):
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        sys.modules.pop("main", None)
        return importlib.import_module("main")

    yield _import
    sys.modules.pop("main", None)


def test_missing_model_uri_fails_startup(import_main):
    with pytest.raises(RuntimeError) as excinfo:
        import_main()
    message = str(excinfo.value)
    assert "MODEL_URI" in message
    assert "byt5-lacunae-v1" in message


def test_blank_model_uri_fails_startup(import_main):
    with pytest.raises(RuntimeError, match="MODEL_URI"):
        import_main(MODEL_URI="   ")


def test_explicit_model_uri_accepted(import_main):
    main = import_main(MODEL_URI="org/byt5-lacunae-v1-ckpt")
    assert main.MODEL_URI == "org/byt5-lacunae-v1-ckpt"


def test_health_reports_resolved_model_uri(import_main):
    from fastapi.testclient import TestClient

    main = import_main(MODEL_URI="org/byt5-lacunae-v1-ckpt")
    with TestClient(main.app) as client:
        body = client.get("/health").json()
    assert body["model_uri"] == "org/byt5-lacunae-v1-ckpt"
    assert body["model_version"] == "byt5-lacunae-v1"
    assert body["model_loaded"] is False
