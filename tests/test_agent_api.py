from pathlib import Path
import asyncio
import json

import httpx
import pytest

pytestmark = pytest.mark.usefixtures("postgres_test_context")

from lingjing_ai.api.app import create_app
from lingjing_ai.config.settings import AppSettings
from lingjing_ai.models.rag import SourceChunk
from lingjing_ai.rag.embeddings import HashingEmbeddingProvider
from lingjing_ai.rag.generator import ExtractiveAnswerGenerator
from lingjing_ai.rag.pipeline import RagPipeline
from lingjing_ai.storage.vector_store import JsonVectorStore


class FakeKnowledgeGraphForAgent:
    def search(self, question: str, top_k: int, scenario: str = "") -> list[SourceChunk]:
        return [
            SourceChunk(
                chunk_id="kg_lingshan_relation",
                document_id="kg_lingshan",
                document_name="知识图谱",
                content="图谱事实：九龙灌浴和灵山大佛同属灵山胜境核心景点。",
                score=0.97,
                metadata={"source_type": "knowledge_graph"},
            )
        ]

    def status(self) -> dict:
        return {"enabled": True, "node_count": 3, "relationship_count": 2, "message": "fake"}


def build_pipeline(tmp_path: Path) -> RagPipeline:
    settings = AppSettings.for_workspace(tmp_path)
    pipeline = RagPipeline(
        settings=settings,
        embedding_provider=HashingEmbeddingProvider(dimensions=64),
        vector_store=JsonVectorStore(tmp_path / "vectors.json"),
        answer_generator=ExtractiveAnswerGenerator(),
    )
    pipeline.ingest_uploaded_text(
        "灵境山资料.md",
        "灵境山适合老人轻松游览，古栈道沿途设有休息点。景区以云海日出和唐代诗路文化闻名。",
    )
    return pipeline


def parse_sse_events(body: str) -> list[dict]:
    events = []
    for line in body.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line.removeprefix("data: ")))
    return events


def test_agent_chat_endpoint_returns_answer_sources_and_tool_trace(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    async def post_chat() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/api/agent/chat", json={"question": "灵境山适合老人游玩吗？"})

    response = asyncio.run(post_chat())
    body = response.json()

    assert response.status_code == 200
    assert body["is_answered"] is True
    assert "### 简要回答" in body["answer"]
    assert body["sources"][0]["document_name"] == "灵境山资料.md"
    assert [trace["tool_name"] for trace in body["tool_trace"]] == [
        "query_rewrite",
        "rag_search",
        "kg_search",
        "document_search",
    ]


def test_agent_chat_uses_knowledge_graph_tool_when_enabled(tmp_path: Path):
    pipeline = build_pipeline(tmp_path)
    pipeline.knowledge_graph = FakeKnowledgeGraphForAgent()
    app = create_app(pipeline)

    async def post_chat() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/api/agent/chat", json={"question": "九龙灌浴和灵山大佛有什么关系？"})

    response = asyncio.run(post_chat())
    body = response.json()

    assert response.status_code == 200
    assert "kg_search" in [trace["tool_name"] for trace in body["tool_trace"]]
    assert body["sources"][0]["document_name"] == "知识图谱"
    assert "同属灵山胜境核心景点" in body["answer"]


def test_agent_chat_autonomously_calls_amap_route_tool(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MAP_API", "map-key")

    def fake_get(url, params, timeout):
        if url.endswith("/v3/geocode/geo"):
            raise AssertionError(f"已发布景点不应调用地理编码：{params['address']}")
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={
                "status": "1",
                "infocode": "10000",
                "route": {
                    "paths": [
                        {
                            "distance": "210",
                            "duration": "180",
                            "steps": [
                                {
                                    "instruction": "沿景区步道前行至五智门",
                                    "polyline": "120.102248,31.421749;120.101292,31.423055",
                                },
                            ],
                        }
                    ]
                },
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    app = create_app(build_pipeline(tmp_path))

    async def post_chat() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/api/agent/chat", json={"question": "从五明桥到五智门怎么走？"})

    response = asyncio.run(post_chat())
    body = response.json()

    assert response.status_code == 200
    assert [trace["tool_name"] for trace in body["tool_trace"]] == ["amap_route"]
    assert body["sources"][0]["document_name"] == "高德路线规划"
    assert "约210米" in body["answer"]
    assert body["sources"][0]["metadata"]["source_type"] == "amap_route"
    assert body["sources"][0]["metadata"]["route_summary"]["mode"] == "walking"
    assert body["sources"][0]["metadata"]["route_summary"]["polyline"] == [
        "120.102248,31.421749",
        "120.101292,31.423055",
    ]


def test_agent_chat_prioritizes_amap_weather_for_scenic_weather_question(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MAP_API", "map-key")
    weather_calls = []

    def fake_get(url, params, timeout):
        weather_calls.append(params["city"])
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={
                "status": "1",
                "infocode": "10000",
                "lives": [
                    {
                        "city": params["city"],
                        "weather": "阴",
                        "temperature": "27",
                        "winddirection": "东南",
                        "windpower": "3",
                        "humidity": "70",
                        "reporttime": "2026-07-08 09:00:00",
                    }
                ],
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    pipeline = build_pipeline(tmp_path)
    pipeline.ingest_uploaded_text(
        "灵山胜境资料.md",
        "# 景区概况\n灵山胜境坐落于江苏省无锡市太湖西北部，是国家5A级旅游景区，以灵山大佛和佛教文化体验闻名。",
    )
    app = create_app(pipeline)

    async def post_chat() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/api/agent/chat", json={"question": "灵山胜境今日的天气如何？"})

    response = asyncio.run(post_chat())
    body = response.json()

    assert response.status_code == 200
    assert weather_calls == ["无锡"]
    assert [trace["tool_name"] for trace in body["tool_trace"]] == ["amap_weather"]
    assert body["sources"][0]["document_name"] == "高德天气"
    assert "无锡当前天气阴" in body["answer"]
    assert "国家5A级旅游景区" not in body["answer"]


def test_agent_chat_uses_history_to_answer_follow_up_question(tmp_path: Path):
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
                "/api/agent/chat",
                json={
                    "question": "那门票呢？",
                    "history": [
                        {"role": "user", "content": "灵山胜境有什么特色？"},
                        {"role": "assistant", "content": "灵山胜境以灵山大佛和梵宫文化体验闻名。"},
                    ],
                },
            )

    response = asyncio.run(post_chat())
    body = response.json()

    assert response.status_code == 200
    assert body["needs_clarification"] is False
    assert body["clarifying_question"] == ""
    assert body["is_answered"] is True
    assert "门票" in body["answer"]
    assert body["sources"][0]["document_name"] == "灵山胜境票务.md"


def test_agent_chat_answers_unclear_five_hour_route_without_clarifying(tmp_path: Path):
    pipeline = build_pipeline(tmp_path)
    pipeline.ingest_uploaded_text(
        "灵山胜境路线.md",
        "灵山胜境五小时游览路线建议经过灵山大佛、九龙灌浴、灵山梵宫，并结合观光车和休息区安排。",
    )
    app = create_app(pipeline)

    async def post_chat() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/api/agent/chat", json={"question": "我览灵山胜境，请帮我规划路线想用五小时游玩时"})

    response = asyncio.run(post_chat())
    body = response.json()

    assert response.status_code == 200
    assert body["needs_clarification"] is False
    assert body["is_answered"] is True
    assert "五小时" in body["answer"]
    assert "普通游客" in body["answer"]


def test_agent_chat_returns_clarifying_question_without_tool_calls(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    async def post_chat() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/api/agent/chat", json={"question": "今日天气如何？"})

    response = asyncio.run(post_chat())
    body = response.json()

    assert response.status_code == 200
    assert body["needs_clarification"] is True
    assert body["clarifying_question"] == "您想查询哪个城市或景区的天气？"
    assert body["answer"] == "您想查询哪个城市或景区的天气？"
    assert body["is_answered"] is False
    assert body["sources"] == []
    assert body["tool_trace"] == []


def test_agent_stream_meta_includes_clarification_fields(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    async def post_stream() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/api/agent/chat/stream", json={"question": "今日天气如何？"})

    response = asyncio.run(post_stream())
    events = parse_sse_events(response.text)
    meta = next(event for event in events if event["type"] == "meta")
    token_text = "".join(event.get("content", "") for event in events if event["type"] == "token")

    assert response.status_code == 200
    assert meta["needs_clarification"] is True
    assert meta["clarifying_question"] == "您想查询哪个城市或景区的天气？"
    assert "您想查询哪个城市或景区的天气？" in token_text


def test_agent_stream_endpoint_returns_status_meta_token_and_done_events(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    async def post_stream() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/api/agent/chat/stream", json={"question": "灵境山适合老人游玩吗？"})

    response = asyncio.run(post_stream())
    events = parse_sse_events(response.text)
    token_text = "".join(event.get("content", "") for event in events if event["type"] == "token")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert events[0]["type"] == "status"
    assert events[0]["message"] == "正在分析问题"
    assert any(event["type"] == "status" and event["message"] == "正在检索资料" for event in events)
    assert any(event["type"] == "meta" and event["is_answered"] is True for event in events)
    assert "### 简要回答" in token_text
    assert events[-1]["type"] == "done"


def test_agent_stream_weather_fast_path_returns_status_and_meta_before_tokens(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MAP_API", "map-key")

    def fake_get(url, params, timeout):
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={
                "status": "1",
                "infocode": "10000",
                "lives": [
                    {
                        "city": params["city"],
                        "weather": "晴",
                        "temperature": "30",
                        "winddirection": "东南",
                        "windpower": "3",
                        "humidity": "60",
                        "reporttime": "2026-07-09 10:00:00",
                    }
                ],
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    app = create_app(build_pipeline(tmp_path))

    async def post_stream() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/api/agent/chat/stream", json={"question": "灵山胜境今日天气如何？"})

    response = asyncio.run(post_stream())
    events = parse_sse_events(response.text)
    meta_index = next(index for index, event in enumerate(events) if event["type"] == "meta")
    token_index = next(index for index, event in enumerate(events) if event["type"] == "token")

    assert response.status_code == 200
    assert events[0] == {"type": "status", "message": "正在查询天气"}
    assert meta_index < token_index
    assert events[meta_index]["tool_trace"][0]["tool_name"] == "amap_weather"
    assert "无锡当前天气晴" in "".join(event.get("content", "") for event in events if event["type"] == "token")
