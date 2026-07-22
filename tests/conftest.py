from __future__ import annotations

import os
import uuid

import pytest

from lingjing_ai.storage.postgres import drop_schema

_SCHEMA_BASES = ("conversations", "attractions", "foods", "feedback")


@pytest.fixture
def postgres_test_context(monkeypatch: pytest.MonkeyPatch):
    """Isolate only integration tests because pure units should not require PostgreSQL."""
    dsn = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    prefix = f"t{uuid.uuid4().hex[:12]}_"
    monkeypatch.setenv("DATABASE_URL", dsn)
    monkeypatch.setenv("DATABASE_SCHEMA_PREFIX", prefix)
    yield {"dsn": dsn, "prefix": prefix}
    for base in _SCHEMA_BASES:
        drop_schema(dsn, f"{prefix}{base}")


@pytest.fixture
def pg_dsn(postgres_test_context) -> str:
    return postgres_test_context["dsn"]


@pytest.fixture
def conversations_schema(postgres_test_context) -> str:
    return f"{postgres_test_context['prefix']}conversations"


@pytest.fixture
def attractions_schema(postgres_test_context) -> str:
    return f"{postgres_test_context['prefix']}attractions"


@pytest.fixture
def foods_schema(postgres_test_context) -> str:
    return f"{postgres_test_context['prefix']}foods"


@pytest.fixture
def feedback_schema(postgres_test_context) -> str:
    return f"{postgres_test_context['prefix']}feedback"
