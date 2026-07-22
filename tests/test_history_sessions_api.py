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
    pipeline = RagPipeline(
        settings=settings,
        embedding_provider=HashingEmbeddingProvider(dimensions=64),
        vector_store=JsonVectorStore(tmp_path / "vectors.json"),
        answer_generator=ExtractiveAnswerGenerator(),
    )
    pipeline.ingest_uploaded_text("灵山胜境概况.md", "灵山胜境以灵山大佛、九龙灌浴和梵宫文化体验闻名。")
    pipeline.ingest_uploaded_text("灵山胜境票务.md", "灵山胜境门票包含成人票、老人票、儿童票等类型，具体优惠以景区公告为准。")
    return pipeline


def parse_sse_events(body: str) -> list[dict]:
    events = []
    for line in body.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line.removeprefix("data: ")))
    return events


def test_chat_without_session_fields_stays_compatible(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    async def post_chat() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/api/rag/chat", json={"question": "灵山胜境有什么特色？"})

    response = asyncio.run(post_chat())
    body = response.json()

    assert response.status_code == 200
    assert body["session_id"] == ""
    assert body["session_title"] == ""
    assert "灵山" in body["answer"]


def test_rag_chat_persists_session_and_uses_backend_history_for_follow_up(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    async def conversation() -> tuple[httpx.Response, httpx.Response, httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            first = await client.post(
                "/api/rag/chat",
                json={"question": "灵山胜境有什么特色？", "visitor_id": "visitor_a"},
            )
            session_id = first.json()["session_id"]
            second = await client.post(
                "/api/rag/chat",
                json={"question": "那门票呢？", "visitor_id": "visitor_a", "session_id": session_id},
            )
            sessions = await client.get("/api/visitor/sessions", params={"visitor_id": "visitor_a"})
            messages = await client.get(f"/api/visitor/sessions/{session_id}/messages", params={"visitor_id": "visitor_a"})
            return first, second, sessions, messages

    first, second, sessions, messages = asyncio.run(conversation())
    session_id = first.json()["session_id"]
    second_body = second.json()

    assert first.status_code == 200
    assert session_id.startswith("sess_")
    assert first.json()["session_title"] == "灵山胜境有什么特色？"
    assert second.status_code == 200
    assert second_body["session_id"] == session_id
    assert "门票" in second_body["answer"]
    assert sessions.json()["sessions"][0]["session_id"] == session_id
    assert [message["role"] for message in messages.json()["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_session_apis_enforce_visitor_ownership_and_delete_single_session(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    async def scenario() -> tuple[httpx.Response, httpx.Response, httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            created = await client.post(
                "/api/rag/chat",
                json={"question": "灵山胜境有什么特色？", "visitor_id": "visitor_a"},
            )
            session_id = created.json()["session_id"]
            blocked = await client.get(f"/api/visitor/sessions/{session_id}/messages", params={"visitor_id": "visitor_b"})
            deleted = await client.delete(f"/api/visitor/sessions/{session_id}", params={"visitor_id": "visitor_a"})
            remaining = await client.get("/api/visitor/sessions", params={"visitor_id": "visitor_a"})
            return created, blocked, deleted, remaining

    created, blocked, deleted, remaining = asyncio.run(scenario())

    assert created.status_code == 200
    assert blocked.status_code == 404
    assert deleted.status_code == 200
    assert deleted.json()["message"] == "会话已删除"
    assert remaining.json()["sessions"] == []


def test_stream_chat_meta_includes_session_fields(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    async def post_stream() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/api/rag/chat/stream",
                json={"question": "灵山胜境有什么特色？", "visitor_id": "visitor_stream"},
            )

    response = asyncio.run(post_stream())
    events = parse_sse_events(response.text)
    meta = next(event for event in events if event["type"] == "meta")

    assert response.status_code == 200
    assert meta["session_id"].startswith("sess_")
    assert meta["session_title"] == "灵山胜境有什么特色？"
