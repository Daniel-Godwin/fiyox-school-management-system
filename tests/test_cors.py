"""CORS — a browser must be able to preflight an upload from the real frontend.

A failing preflight is invisible to JavaScript (it only ever sees
"Failed to fetch"), so these are worth pinning down explicitly.
"""
import importlib
import os

import pytest
from fastapi.testclient import TestClient

VERCEL = "https://fiyox-school-management-system-oskb.vercel.app"


def _client_with_origin(origin_setting: str) -> TestClient:
    os.environ["FRONTEND_ORIGIN"] = origin_setting
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    import app.core.config as config
    import app.main as main
    importlib.reload(config)
    importlib.reload(main)
    return TestClient(main.app)


def _preflight(client: TestClient, origin: str):
    return client.options("/api/schools/me/branding/logo", headers={
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    })


@pytest.mark.parametrize("configured", [
    VERCEL,            # exactly right
    VERCEL + "/",      # with a trailing slash — an easy mistake in a dashboard
    f" {VERCEL} ",     # with stray whitespace
])
def test_upload_preflight_succeeds_from_the_frontend(configured):
    client = _client_with_origin(configured)
    r = _preflight(client, VERCEL)
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == VERCEL
    assert "POST" in r.headers.get("access-control-allow-methods", "")


def test_unknown_origin_is_refused():
    client = _client_with_origin(VERCEL)
    r = _preflight(client, "https://not-your-site.example.com")
    assert r.headers.get("access-control-allow-origin") is None


def test_wildcard_still_works_for_local_dev():
    client = _client_with_origin("*")
    r = _preflight(client, "http://localhost:3000")
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") is not None
