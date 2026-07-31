from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
import httpx
import pytest

from lingjing_ai.api.guided_tour_speech_routes import build_guided_tour_speech_router
from lingjing_ai.guided_tour.catalog import GuidedTourCatalog
from lingjing_ai.guided_tour.speech import (
    GuidedTourSpeechService,
    NarrationSpeechError,
    NarrationSpeechUnavailable,
    XIAOXIAO_VOICE,
)

from test_guided_tour_catalog import route_payload


class FakeResponse:
    def __init__(self, status_code=200, content=b"mp3", content_type="audio/mpeg"):
        self.status_code = status_code
        self.content = content
        self.headers = {"content-type": content_type}


class FakeAttractionStore:
    def __init__(self):
        self.records = {
            "published": SimpleNamespace(status="published", summary="公开景点摘要。"),
            "empty": SimpleNamespace(status="published", summary=""),
        }

    def get_attraction(self, attraction_id: str, public_only: bool = False):
        record = self.records.get(attraction_id)
        if public_only and getattr(record, "status", "") != "published":
            return None
        return record


def catalog(tmp_path: Path) -> GuidedTourCatalog:
    path = tmp_path / "guided-tour.json"
    path.write_text(json.dumps(route_payload(), ensure_ascii=False), encoding="utf-8")
    return GuidedTourCatalog(path)


def test_speech_service_uses_fixed_xiaoxiao_voice_and_escapes_ssml():
    captured = []

    async def requester(url, *, headers, content, timeout):
        captured.append((url, headers, content.decode("utf-8"), timeout))
        return FakeResponse()

    service = GuidedTourSpeechService(
        enabled=True,
        subscription_key="secret-key",
        region="eastasia",
        requester=requester,
    )
    audio = asyncio.run(service.synthesize("灵山 <平安> & 吉祥"))

    assert audio == b"mp3"
    url, headers, ssml, timeout = captured[0]
    assert url == "https://eastasia.tts.speech.microsoft.com/cognitiveservices/v1"
    assert headers["Ocp-Apim-Subscription-Key"] == "secret-key"
    assert headers["X-Microsoft-OutputFormat"] == "audio-24khz-48kbitrate-mono-mp3"
    assert f'name="{XIAOXIAO_VOICE}"' in ssml
    assert "&lt;平安&gt; &amp; 吉祥" in ssml
    assert timeout <= 10


def test_speech_service_has_sanitized_unavailable_and_upstream_errors():
    disabled = GuidedTourSpeechService(enabled=False, subscription_key="", region="")
    with pytest.raises(NarrationSpeechUnavailable, match="未配置"):
        asyncio.run(disabled.synthesize("讲解"))

    async def failing_requester(*args, **kwargs):
        return FakeResponse(status_code=500, content=b"secret-key leaked", content_type="text/plain")

    failing = GuidedTourSpeechService(
        enabled=True,
        subscription_key="secret-key",
        region="eastasia",
        requester=failing_requester,
    )
    with pytest.raises(NarrationSpeechError) as captured:
        asyncio.run(failing.synthesize("讲解"))
    assert "secret-key" not in str(captured.value)


def test_speech_service_rejects_unsafe_region_before_request():
    service = GuidedTourSpeechService(
        enabled=True,
        subscription_key="secret",
        region="eastasia.example.com/path",
    )
    with pytest.raises(NarrationSpeechUnavailable, match="区域"):
        asyncio.run(service.synthesize("讲解"))


def test_speech_routes_accept_only_catalog_stops_or_published_attractions(tmp_path: Path):
    calls = []

    class FakeSpeech:
        async def synthesize(self, text: str) -> bytes:
            calls.append(text)
            return b"audio"

    app = FastAPI()
    app.include_router(
        build_guided_tour_speech_router(catalog(tmp_path), FakeAttractionStore(), FakeSpeech())
    )

    async def request(path: str, json_body=None):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return await client.post(path, json=json_body)

    stop = asyncio.run(request("/api/visitor/guided-tour/narrations/stops/stop-1/synthesize"))
    attraction = asyncio.run(
        request("/api/visitor/guided-tour/narrations/attractions/published/synthesize")
    )
    unknown = asyncio.run(
        request("/api/visitor/guided-tour/narrations/attractions/missing/synthesize")
    )
    arbitrary = asyncio.run(
        request(
            "/api/visitor/guided-tour/narrations/stops/stop-1/synthesize",
            {"text": "替换讲解", "voice": "other"},
        )
    )

    assert stop.status_code == 200 and stop.headers["content-type"].startswith("audio/mpeg")
    assert attraction.status_code == 200
    assert unknown.status_code == 404
    assert arbitrary.status_code == 200
    assert calls == ["九龙灌浴的固定讲解词。", "公开景点摘要。", "九龙灌浴的固定讲解词。"]
    assert "替换讲解" not in calls


def test_speech_route_maps_disabled_service_to_503(tmp_path: Path):
    app = FastAPI()
    app.include_router(
        build_guided_tour_speech_router(
            catalog(tmp_path),
            FakeAttractionStore(),
            GuidedTourSpeechService(enabled=False, subscription_key="", region=""),
        )
    )

    async def request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/visitor/guided-tour/narrations/stops/stop-1/synthesize"
            )

    response = asyncio.run(request())
    assert response.status_code == 503
    assert "未配置" in response.json()["detail"]
