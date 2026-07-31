from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI
import httpx

from lingjing_ai.api.guided_tour_routes import build_guided_tour_router
from lingjing_ai.guided_tour.catalog import GuidedTourCatalog

from test_guided_tour_catalog import route_payload


def test_classic_route_api_exposes_only_public_catalog_data(tmp_path: Path):
    path = tmp_path / "guided-tour.json"
    path.write_text(json.dumps(route_payload(), ensure_ascii=False), encoding="utf-8")
    app = FastAPI()
    app.include_router(build_guided_tour_router(GuidedTourCatalog(path)))

    async def request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return await client.get("/api/visitor/guided-tour/classic")

    response = asyncio.run(request())
    assert response.status_code == 200
    body = response.json()
    assert body["route_id"] == "lingshan-classic-v1"
    assert len(body["stops"]) == 6
    serialized = response.text.lower()
    assert str(path).lower() not in serialized
    assert "speech_key" not in serialized
    assert "azure" not in serialized
