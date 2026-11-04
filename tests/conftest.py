"""Opt-in fixtures for tests of compatibility endpoints."""

import pytest


@pytest.fixture
def asserted_api(monkeypatch):
    """Exercise legacy header-based requests while verified suites keep their own mode."""
    monkeypatch.setenv("PORTWATCH_IDENTITY_MODE", "asserted")


@pytest.fixture
def fictional_fleet(monkeypatch):
    """Supply carrier data for tests whose assertions concern downstream policy."""
    from backend.app.routes import company
    from src.portwatch_os.fleet.company import demo_company

    profile = demo_company()
    monkeypatch.setattr(company, "resolve_company", lambda company_id=None: profile)
