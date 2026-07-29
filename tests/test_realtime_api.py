from pathlib import Path

import asyncio
import json

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
    pipeline.ingest_uploaded_text(
        "灵山胜境概况.md",
        "灵山胜境以灵山大佛、九龙灌浴和梵宫文化体验闻名。",
    )
    return pipeline


class FakeWebSocket:
    def __init__(self, incoming=None) -> None:
        self.incoming = list(incoming or [])
        self.events = []
        self.accepted = False
        self.closed = None

    async def accept(self):
        self.accepted = True

    async def send_json(self, event):
        self.events.append(event)

    async def send_bytes(self, payload):
        self.events.append({"type": "binary", "payload": payload})

    async def receive(self):
        if self.incoming:
            event = self.incoming.pop(0)
            return {"type": "websocket.receive", "text": json.dumps(event), "bytes": None}
        return {"type": "websocket.disconnect", "code": 1000}

    async def close(self, code=1000):
        self.closed = code


def realtime_endpoint(app):
    for route in app.routes:
        candidates = getattr(getattr(route, "original_router", None), "routes", [route])
        for candidate in candidates:
            if getattr(candidate, "path", "") == "/api/visitor/realtime":
                return candidate.endpoint
    raise LookupError("Realtime WebSocket route is not registered.")


def test_realtime_websocket_falls_back_to_text_and_persists_complete_turn(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    websocket = FakeWebSocket(
        [{"type": "text.submit", "turn_id": "turn_1", "text": "灵山胜境有什么特色？"}]
    )

    asyncio.run(realtime_endpoint(app)(websocket, visitor_id="visitor_ws", session_id=""))

    ready = next(event for event in websocket.events if event["type"] == "session.ready")
    completed = next(event for event in websocket.events if event["type"] == "turn.completed")
    assert ready["upstream_available"] is False
    assert any(event["type"] == "agent.meta" for event in websocket.events)
    assert any(event["type"] == "assistant.text.done" for event in websocket.events)

    async def load_messages():
        import httpx

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(
                f"/api/visitor/sessions/{completed['session_id']}/messages",
                params={"visitor_id": "visitor_ws"},
            )

    response = asyncio.run(load_messages())
    assert [message["role"] for message in response.json()["messages"]] == ["user", "assistant"]


def test_realtime_websocket_rejects_session_owned_by_another_visitor(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    async def create_session():
        import httpx

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/api/rag/chat",
                json={"question": "灵山胜境有什么特色？", "visitor_id": "visitor_a"},
            )

    session_id = asyncio.run(create_session()).json()["session_id"]
    websocket = FakeWebSocket()

    asyncio.run(
        realtime_endpoint(app)(websocket, visitor_id="visitor_b", session_id=session_id)
    )

    assert websocket.events[0]["type"] == "error"
    assert websocket.events[0]["code"] == "SESSION_FORBIDDEN"
    assert websocket.closed == 1008


def test_realtime_websocket_rejects_an_unknown_initial_avatar(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))
    websocket = FakeWebSocket()

    asyncio.run(
        realtime_endpoint(app)(
            websocket,
            visitor_id="visitor_a",
            session_id="",
            avatar_id="remote-model",
        )
    )

    assert websocket.events[0]["type"] == "error"
    assert websocket.events[0]["code"] == "INVALID_AVATAR"
    assert websocket.closed == 1008
