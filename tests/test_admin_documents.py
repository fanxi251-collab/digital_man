from pathlib import Path
import asyncio
import json

import httpx
import pytest

pytestmark = pytest.mark.usefixtures("postgres_test_context")

from lingjing_ai.api.app import create_app
from lingjing_ai.config.settings import AppSettings
from lingjing_ai.rag.embeddings import HashingEmbeddingProvider
from lingjing_ai.rag.generator import ExtractiveAnswerGenerator
from lingjing_ai.rag.pipeline import RagPipeline
from lingjing_ai.storage.vector_store import JsonVectorStore


def build_pipeline(tmp_path: Path) -> RagPipeline:
    settings = AppSettings.for_workspace(tmp_path)
    return RagPipeline(
        settings=settings,
        embedding_provider=HashingEmbeddingProvider(dimensions=64),
        vector_store=JsonVectorStore(tmp_path / "vectors.json"),
        answer_generator=ExtractiveAnswerGenerator(),
    )


def test_existing_upload_writes_document_manifest(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    async def upload() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/api/rag/documents/upload",
                files={"file": ("游客服务.md", "游客服务中心提供婴儿车租赁。", "text/markdown")},
            )

    response = asyncio.run(upload())
    manifest_path = tmp_path / "data" / "document_manifest.json"
    records = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert response.status_code == 200
    assert records[0]["document_name"] == "游客服务.md"
    assert records[0]["indexed_chunks"] == 1
    assert records[0]["saved_path"].endswith(".md")


def test_admin_documents_list_and_preview_uploaded_material(tmp_path: Path):
    pipeline = build_pipeline(tmp_path)
    document = pipeline.ingest_uploaded_text("灵境山资料.md", "灵境山以云海日出和古栈道闻名。")
    app = create_app(pipeline)

    async def list_and_preview() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            listing = await client.get("/api/admin/documents")
            preview = await client.get(f"/api/admin/documents/{document.id}/content")
            return listing, preview

    list_response, preview_response = asyncio.run(list_and_preview())
    documents = list_response.json()["documents"]

    assert list_response.status_code == 200
    assert documents[0]["document_id"] == document.id
    assert documents[0]["document_name"] == "灵境山资料.md"
    assert documents[0]["file_size"] > 0
    assert preview_response.status_code == 200
    assert preview_response.json()["content"] == "灵境山以云海日出和古栈道闻名。"


def test_admin_reindex_updates_vectors_and_invalidates_cache(tmp_path: Path):
    pipeline = build_pipeline(tmp_path)
    document = pipeline.ingest_uploaded_text("游客服务.md", "游客服务中心提供婴儿车租赁。")
    first = pipeline.ask("游客服务中心提供什么？")
    Path(document.path).write_text("游客服务中心提供失物招领服务。", encoding="utf-8")
    app = create_app(pipeline)

    async def reindex() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(f"/api/admin/documents/{document.id}/reindex")

    response = asyncio.run(reindex())
    second = pipeline.ask("游客服务中心提供什么？")

    assert response.status_code == 200
    assert "婴儿车租赁" in first.answer
    assert "失物招领" in second.answer


def test_admin_delete_removes_single_document_file_manifest_and_vectors(tmp_path: Path):
    pipeline = build_pipeline(tmp_path)
    document = pipeline.ingest_uploaded_text("游客服务.md", "游客服务中心提供婴儿车租赁。")
    saved_path = Path(document.path)
    app = create_app(pipeline)

    async def delete_document() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.delete(f"/api/admin/documents/{document.id}")

    response = asyncio.run(delete_document())
    result = pipeline.ask("哪里可以租婴儿车？")
    manifest_records = json.loads((tmp_path / "data" / "document_manifest.json").read_text(encoding="utf-8"))

    assert response.status_code == 200
    assert saved_path.exists() is False
    assert manifest_records == []
    assert result.is_answered is False


def test_admin_document_content_returns_404_for_missing_document(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    async def preview_missing() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/api/admin/documents/missing/content")

    response = asyncio.run(preview_missing())

    assert response.status_code == 404


def test_admin_knowledge_graph_status_reports_disabled_by_default(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    async def get_status() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/api/admin/knowledge-graph/status")

    response = asyncio.run(get_status())
    body = response.json()

    assert response.status_code == 200
    assert body["enabled"] is False
    assert body["node_count"] == 0
    assert body["relationship_count"] == 0
    assert body["schema_version"] == "scenic_v1"
