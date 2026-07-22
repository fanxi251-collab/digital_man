import asyncio
import json
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.usefixtures("postgres_test_context")

from lingjing_ai.api.app import create_app
from lingjing_ai.config.settings import AppSettings
from lingjing_ai.rag.embeddings import HashingEmbeddingProvider
from lingjing_ai.rag.generator import ExtractiveAnswerGenerator
from lingjing_ai.rag.pipeline import RagPipeline
from lingjing_ai.services.analytics_snapshot import AnalyticsSnapshotError, AnalyticsSnapshotStore
from lingjing_ai.storage.vector_store import JsonVectorStore


REQUIRED_SECTIONS = {
    "metadata": {"schema_version": "tourism_analytics_v1", "row_count": 3},
    "kpis": {"visit_count": 3},
    "monthly_trend": [],
    "demographics": {},
    "attraction_types": [],
    "attraction_rankings": {},
    "consumption": {},
    "satisfaction": {},
    "insights": [],
    "quality": {},
}


def build_pipeline(tmp_path: Path) -> RagPipeline:
    settings = AppSettings.for_workspace(tmp_path)
    return RagPipeline(
        settings=settings,
        embedding_provider=HashingEmbeddingProvider(dimensions=64),
        vector_store=JsonVectorStore(tmp_path / "vectors.json"),
        answer_generator=ExtractiveAnswerGenerator(),
    )


def request_path(app, path: str) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(path)

    return asyncio.run(send())


def write_snapshot(tmp_path: Path, payload: dict | None = None) -> Path:
    path = tmp_path / "data" / "tourism_analytics_snapshot.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload or REQUIRED_SECTIONS, ensure_ascii=False), encoding="utf-8")
    return path


def test_snapshot_store_loads_required_dashboard_sections(tmp_path: Path):
    store = AnalyticsSnapshotStore(write_snapshot(tmp_path))

    assert store.load() == REQUIRED_SECTIONS


@pytest.mark.parametrize(
    "payload",
    [
        {**REQUIRED_SECTIONS, "metadata": {"schema_version": "old_version"}},
        {key: value for key, value in REQUIRED_SECTIONS.items() if key != "quality"},
    ],
)
def test_snapshot_store_rejects_incompatible_or_incomplete_payload(tmp_path: Path, payload: dict):
    store = AnalyticsSnapshotStore(write_snapshot(tmp_path, payload))

    with pytest.raises(AnalyticsSnapshotError):
        store.load()


def test_snapshot_store_rejects_malformed_json(tmp_path: Path):
    path = write_snapshot(tmp_path)
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(AnalyticsSnapshotError):
        AnalyticsSnapshotStore(path).load()


def test_admin_analytics_api_returns_snapshot(tmp_path: Path):
    write_snapshot(tmp_path)
    app = create_app(build_pipeline(tmp_path), seed_attractions=False)

    response = request_path(app, "/api/admin/analytics/dashboard")

    assert response.status_code == 200
    assert response.json() == REQUIRED_SECTIONS


def test_admin_analytics_api_returns_503_with_build_command_when_snapshot_missing(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path), seed_attractions=False)

    response = request_path(app, "/api/admin/analytics/dashboard")

    assert response.status_code == 503
    assert "build_tourism_analytics_snapshot.py" in response.json()["detail"]


def test_admin_analytics_api_returns_503_for_invalid_snapshot(tmp_path: Path):
    write_snapshot(tmp_path, {"metadata": {"schema_version": "broken"}})
    app = create_app(build_pipeline(tmp_path), seed_attractions=False)

    response = request_path(app, "/api/admin/analytics/dashboard")

    assert response.status_code == 503
    assert "快照" in response.json()["detail"]
