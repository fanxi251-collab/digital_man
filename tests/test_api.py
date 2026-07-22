from pathlib import Path
import asyncio
from dataclasses import replace

import httpx
import pytest

pytestmark = pytest.mark.usefixtures("postgres_test_context")

from lingjing_ai.api.app import create_app
from lingjing_ai.config.settings import AppSettings
from lingjing_ai.rag.embeddings import HashingEmbeddingProvider
from lingjing_ai.rag.generator import ExtractiveAnswerGenerator
from lingjing_ai.rag.pipeline import RagPipeline
from lingjing_ai.storage.qdrant_vector_store import QdrantVectorStore


def build_pipeline(tmp_path: Path) -> RagPipeline:
    settings = AppSettings.for_workspace(tmp_path)
    pipeline = RagPipeline(
        settings=settings,
        embedding_provider=HashingEmbeddingProvider(dimensions=64),
        vector_store=QdrantVectorStore(
            path=settings.qdrant_db_dir,
            collection_name=settings.vector_collection_name,
            vector_size=64,
        ),
        answer_generator=ExtractiveAnswerGenerator(),
    )
    pipeline.ingest_text("灵境山资料.md", "灵境山以云海日出和古栈道闻名。")
    return pipeline


def test_create_app_requires_database_url(tmp_path: Path):
    pipeline = build_pipeline(tmp_path)
    pipeline.settings = replace(pipeline.settings, database_url="")

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_app(pipeline)


def test_chat_endpoint_returns_rag_answer(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    async def post_chat() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/api/rag/chat", json={"question": "灵境山有什么特色？"})

    response = asyncio.run(post_chat())

    assert response.status_code == 200
    body = response.json()
    assert body["is_answered"] is True
    assert "云海日出" in body["answer"]
    assert body["sources"][0]["document_name"] == "灵境山资料.md"


def test_upload_document_indexes_text_and_chat_can_use_it(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    async def upload_and_chat() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            upload = await client.post(
                "/api/rag/documents/upload",
                files={"file": ("青岚湖资料.md", "青岚湖适合乘船观景，湖畔栈桥是热门拍照点。", "text/markdown")},
            )
            chat = await client.post("/api/rag/chat", json={"question": "青岚湖适合做什么？"})
            return upload, chat

    upload_response, chat_response = asyncio.run(upload_and_chat())
    upload_body = upload_response.json()
    chat_body = chat_response.json()

    assert upload_response.status_code == 200
    assert upload_body["document_name"] == "青岚湖资料.md"
    assert upload_body["indexed_chunks"] == 1
    assert upload_body["vector_store"].endswith("qdrant_db")
    assert chat_response.status_code == 200
    assert chat_body["is_answered"] is True
    assert "乘船观景" in chat_body["answer"]


def test_upload_document_rejects_unsupported_empty_and_non_utf8_files(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    async def post_upload(filename: str, content: bytes | str) -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/api/rag/documents/upload",
                files={"file": (filename, content, "application/octet-stream")},
            )

    pdf_response = asyncio.run(post_upload("资料.pdf", b"%PDF-1.4"))
    empty_response = asyncio.run(post_upload("空资料.md", ""))
    invalid_response = asyncio.run(post_upload("乱码.txt", b"\xff\xfe\x00"))

    assert pdf_response.status_code == 400
    assert "仅支持" in pdf_response.json()["detail"]
    assert empty_response.status_code == 400
    assert "不能为空" in empty_response.json()["detail"]
    assert invalid_response.status_code == 400
    assert "UTF-8" in invalid_response.json()["detail"]


def test_rag_chat_uses_history_to_rewrite_follow_up_question(tmp_path: Path):
    pipeline = build_pipeline(tmp_path)
    pipeline.ingest_uploaded_text(
        "灵山胜境票务.md",
        "灵山胜境门票包含成人票、老人票、儿童票等类型，具体优惠政策以景区公告为准。",
    )
    app = create_app(pipeline)

    async def post_chat() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/api/rag/chat",
                json={
                    "question": "那门票呢？",
                    "history": [{"role": "user", "content": "灵山胜境有什么特色？"}],
                },
            )

    response = asyncio.run(post_chat())
    body = response.json()

    assert response.status_code == 200
    assert body["needs_clarification"] is False
    assert body["is_answered"] is True
    assert "门票" in body["answer"]
