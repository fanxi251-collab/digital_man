from pathlib import Path
import asyncio

import httpx
import pytest

pytestmark = pytest.mark.usefixtures("postgres_test_context")

from lingjing_ai.api.app import _build_agent_executor, create_app
from lingjing_ai.config.settings import AppSettings
from lingjing_ai.rag.embeddings import HashingEmbeddingProvider
from lingjing_ai.rag.generator import ExtractiveAnswerGenerator
from lingjing_ai.rag.pipeline import RagPipeline
from lingjing_ai.storage.vector_store import JsonVectorStore
from lingjing_ai.services.attraction_store import AttractionStore


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


def build_pipeline(tmp_path: Path) -> RagPipeline:
    settings = AppSettings.for_workspace(tmp_path)
    return RagPipeline(
        settings=settings,
        embedding_provider=HashingEmbeddingProvider(dimensions=64),
        vector_store=JsonVectorStore(tmp_path / "vectors.json"),
        answer_generator=ExtractiveAnswerGenerator(),
    )


def test_map_config_api_returns_frontend_map_settings(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MAP_JS_API", "js-map-key")
    monkeypatch.setenv("MAP_JS_SECURITY_CODE", "js-security-code")
    app = create_app(build_pipeline(tmp_path))

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/api/tools/map/config")

    response = asyncio.run(request())
    body = response.json()

    assert response.status_code == 200
    assert body["enabled"] is True
    assert body["js_api_key"] == "js-map-key"
    assert body["security_js_code"] == "js-security-code"
    assert body["map_style"] == "amap://styles/normal"
    assert body["default_route_mode"] == "driving"


def test_map_config_api_allows_custom_map_style(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MAP_JS_API", "js-map-key")
    monkeypatch.setenv("MAP_JS_SECURITY_CODE", "js-security-code")
    monkeypatch.setenv("MAP_JS_STYLE", "amap://styles/fresh")
    app = create_app(build_pipeline(tmp_path))

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/api/tools/map/config")

    response = asyncio.run(request())
    body = response.json()

    assert response.status_code == 200
    assert body["map_style"] == "amap://styles/fresh"


def test_map_config_api_requires_js_security_code(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MAP_JS_API", "js-map-key")
    monkeypatch.delenv("MAP_JS_SECURITY_CODE", raising=False)
    app = create_app(build_pipeline(tmp_path))

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/api/tools/map/config")

    response = asyncio.run(request())
    body = response.json()

    assert response.status_code == 200
    assert body["enabled"] is False
    assert "MAP_JS_SECURITY_CODE" in body["message"]


def test_weather_api_returns_amap_weather(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MAP_API", "map-key")

    def fake_get(url, params, timeout):
        return FakeResponse(
            {
                "status": "1",
                "infocode": "10000",
                "lives": [
                    {
                        "city": params["city"],
                        "weather": "晴",
                        "temperature": "29",
                        "winddirection": "东",
                        "windpower": "3",
                        "humidity": "58",
                        "reporttime": "2026-07-07 12:00:00",
                    }
                ],
            }
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    app = create_app(build_pipeline(tmp_path))

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/api/tools/weather", params={"city": "无锡"})

    response = asyncio.run(request())
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ok"
    assert "无锡当前天气晴" in body["content"]


def test_map_search_api_returns_amap_place_results(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MAP_API", "map-key")

    def fake_get(url, params, timeout):
        return FakeResponse(
            {
                "status": "1",
                "infocode": "10000",
                "pois": [
                    {
                        "name": params["keywords"],
                        "type": "风景名胜",
                        "address": "马山镇",
                        "location": "120.100,31.500",
                    }
                ],
            }
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    app = create_app(build_pipeline(tmp_path))

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/api/tools/map/search", params={"keywords": "灵山胜境", "city": "无锡"})

    response = asyncio.run(request())
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ok"
    assert "灵山胜境" in body["content"]


def test_map_route_api_rejects_endpoint_outside_scenic_navigation_area(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MAP_API", "map-key")
    direction_calls = []

    def fake_get(url, params, timeout):
        if url.endswith("/v3/geocode/geo"):
            locations = {
                "无锡站": "120.305,31.590",
                "灵山胜境": "120.100,31.500",
            }
            return FakeResponse(
                {
                    "status": "1",
                    "infocode": "10000",
                    "geocodes": [{"formatted_address": params["address"], "location": locations[params["address"]]}],
                }
            )
        direction_calls.append(url)
        return FakeResponse(
            {
                "status": "1",
                "infocode": "10000",
                "route": {
                    "paths": [
                        {
                            "distance": "42000",
                            "duration": "3600",
                            "steps": [
                                {"instruction": "从无锡站出发", "polyline": "120.305,31.590;120.200,31.550"},
                                {"instruction": "到达灵山胜境", "polyline": "120.200,31.550;120.100,31.500"},
                            ],
                        }
                    ]
                },
            }
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    app = create_app(build_pipeline(tmp_path))

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(
                "/api/tools/map/route",
                params={"origin": "无锡站", "destination": "灵山胜境", "mode": "driving"},
            )

    response = asyncio.run(request())
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "error"
    assert "起点" in body["message"]
    assert "10公里" in body["message"]
    assert body["content"] == ""
    assert "route_summary" not in body["data"]
    assert direction_calls == []


def test_map_route_api_uses_structured_locations_without_geocoding(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MAP_API", "map-key")
    requested_paths = []

    def fake_get(url, params, timeout):
        requested_paths.append(url)
        assert params["origin"] == "120.102248,31.421749"
        assert params["destination"] == "120.096477,31.430194"
        return FakeResponse(
            {
                "status": "1",
                "route": {
                    "paths": [
                        {
                            "distance": "1200",
                            "duration": "900",
                            "steps": [{"instruction": "沿景区步道前行", "polyline": "120.102248,31.421749;120.096477,31.430194"}],
                        }
                    ]
                },
            }
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    app = create_app(build_pipeline(tmp_path))

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(
                "/api/tools/map/route",
                params={
                    "origin": "五明桥",
                    "destination": "灵山大佛",
                    "origin_location": "120.102248,31.421749",
                    "destination_location": "120.096477,31.430194",
                    "mode": "walking",
                },
            )

    response = asyncio.run(request())

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert all("/v3/geocode/geo" not in path for path in requested_paths)


def test_map_route_api_resolves_published_internal_names_and_defaults_to_walking(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setenv("MAP_API", "map-key")
    requested_paths = []

    def fake_get(url, params, timeout):
        requested_paths.append(url)
        assert "/v3/geocode/geo" not in url
        assert url.endswith("/v3/direction/walking")
        assert params["origin"] == "120.102248,31.421749"
        assert params["destination"] == "120.101292,31.423055"
        return FakeResponse(
            {
                "status": "1",
                "route": {
                    "paths": [{
                        "distance": "210",
                        "duration": "180",
                        "steps": [{
                            "instruction": "沿景区步道向北步行",
                            "polyline": f"{params['origin']};{params['destination']}",
                        }],
                    }]
                },
            }
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    app = create_app(build_pipeline(tmp_path))

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(
                "/api/tools/map/route",
                params={"origin": "五明桥", "destination": "五智门"},
            )

    response = asyncio.run(request())
    summary = response.json()["data"]["route_summary"]

    assert response.status_code == 200
    assert requested_paths == ["https://restapi.amap.com/v3/direction/walking"]
    assert summary["mode"] == "walking"
    assert summary["origin_location"] == "120.102248,31.421749"
    assert summary["destination_location"] == "120.101292,31.423055"


def test_agent_route_tool_receives_published_attraction_location_resolver(
    tmp_path: Path, pg_dsn: str, attractions_schema: str
):
    pipeline = build_pipeline(tmp_path)
    store = AttractionStore(
        pg_dsn,
        tmp_path / "attraction_images",
        seed_on_empty=True,
        schema=attractions_schema,
    )

    executor = _build_agent_executor(pipeline, store)
    route_tool = executor.tools["amap_route"]

    assert route_tool.location_resolver("五明桥") == "120.102248,31.421749"
    assert route_tool.location_resolver("五智门") == "120.101292,31.423055"
    assert route_tool.location_resolver("不存在景点") is None
    assert route_tool.scope_validator is not None
    assert route_tool.scope_validator(
        "120.102248,31.421749",
        "120.101292,31.423055",
    ).allowed is True
    assert route_tool.scope_validator(
        "120.102248,31.421749",
        "120.305000,31.590000",
    ).allowed is False
