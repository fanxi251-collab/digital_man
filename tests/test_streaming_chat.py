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


def parse_sse_events(body: str) -> list[dict]:
    events = []
    for line in body.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line.removeprefix("data: ")))
    return events


def test_stream_chat_endpoint_returns_meta_token_and_done_events(tmp_path: Path):
    pipeline = build_pipeline(tmp_path)
    pipeline.ingest_text("灵境山资料.md", "灵境山以云海日出和古栈道闻名。")
    app = create_app(pipeline)

    async def post_stream() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/api/rag/chat/stream", json={"question": "灵境山有什么特色？"})

    response = asyncio.run(post_stream())
    events = parse_sse_events(response.text)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert events[0]["type"] == "meta"
    assert events[0]["is_answered"] is True
    assert events[0]["sources"][0]["document_name"] == "灵境山资料.md"
    assert any(event["type"] == "token" and "云海日出" in event["content"] for event in events)
    assert events[-1]["type"] == "done"
    assert events[-1]["trace_id"] == events[0]["trace_id"]


def test_stream_chat_endpoint_streams_refusal_when_no_material_matches(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    async def post_stream() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/api/rag/chat/stream", json={"question": "熊猫馆开放时间是什么？"})

    response = asyncio.run(post_stream())
    events = parse_sse_events(response.text)
    token_text = "".join(event["content"] for event in events if event["type"] == "token")

    assert response.status_code == 200
    assert events[0]["type"] == "meta"
    assert events[0]["is_answered"] is False
    assert "当前资料中没有查到可靠依据" in token_text
    assert events[-1]["type"] == "done"


def test_stream_chat_includes_default_assumptions_for_route_planning(tmp_path: Path):
    pipeline = build_pipeline(tmp_path)
    pipeline.ingest_uploaded_text(
        "灵山胜境路线.md",
        "灵山胜境五小时游览路线建议经过灵山大佛、九龙灌浴、灵山梵宫，并结合观光车和休息区安排。",
    )
    app = create_app(pipeline)

    async def post_stream() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/api/rag/chat/stream",
                json={"question": "我览灵山胜境，请帮我规划路线想用五小时游玩时"},
            )

    response = asyncio.run(post_stream())
    events = parse_sse_events(response.text)
    token_text = "".join(event["content"] for event in events if event["type"] == "token")

    assert response.status_code == 200
    assert "五小时" in token_text
    assert "普通游客" in token_text
