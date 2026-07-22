import asyncio
from pathlib import Path

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


async def request(app, method: str, url: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, url, **kwargs)


def food_payload(status: str = "draft") -> dict:
    return {
        "name": "灵山蔬食馆",
        "summary": "景区内的江南风味餐饮地点。",
        "description": "提供素面、素包等灵山风味。",
        "scope": "inside",
        "category": "素食",
        "taste_tags": ["清淡"],
        "signature_dishes": ["灵山素面"],
        "price_level": 2,
        "vegetarian_friendly": True,
        "address": "灵山胜境景区内",
        "opening_hours": "以景区当日公告为准",
        "longitude": 120.101,
        "latitude": 31.426,
        "source_url": "https://www.lingshan.com.cn/",
        "verified_at": "2026-07-19",
        "is_featured": True,
        "sort_order": 1,
        "status": status,
    }


def test_food_admin_publish_and_public_filters(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path), seed_attractions=False, seed_foods=False)
    created = asyncio.run(request(app, "POST", "/api/admin/foods", json=food_payload()))
    food_id = created.json()["food_id"]
    blocked = asyncio.run(request(app, "PUT", f"/api/admin/foods/{food_id}", json=food_payload("published")))
    uploaded = asyncio.run(
        request(
            app,
            "POST",
            f"/api/admin/foods/{food_id}/images",
            params={"is_cover": "true"},
            files={"file": ("cover.webp", b"RIFF-food-WEBP", "image/webp")},
        )
    )
    published = asyncio.run(request(app, "PUT", f"/api/admin/foods/{food_id}", json=food_payload("published")))
    listing = asyncio.run(
        request(
            app,
            "GET",
            "/api/visitor/foods",
            params={"scope": "inside", "taste": "清淡", "vegetarian": "true"},
        )
    )

    assert created.status_code == 201
    assert blocked.status_code == 400 and "封面" in blocked.json()["detail"]
    assert uploaded.status_code == 201
    assert published.status_code == 200
    assert [item["food_id"] for item in listing.json()["foods"]] == [food_id]


def test_feedback_api_is_idempotent_private_and_manageable(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path), seed_attractions=False, seed_foods=False)
    payload = {
        "visitor_id": "visitor_alpha",
        "request_id": "request_1",
        "rating": 4,
        "category": "service",
        "content": "工作人员指引耐心，希望增加休息座椅。",
        "contact": "visitor@example.com",
    }

    created = asyncio.run(request(app, "POST", "/api/visitor/feedback", json=payload))
    repeated = asyncio.run(request(app, "POST", "/api/visitor/feedback", json=payload))
    visitor_list = asyncio.run(
        request(app, "GET", "/api/visitor/feedback", params={"visitor_id": "visitor_alpha"})
    )
    admin_list = asyncio.run(request(app, "GET", "/api/admin/feedback", params={"status": "pending"}))
    updated = asyncio.run(
        request(
            app,
            "PATCH",
            f"/api/admin/feedback/{created.json()['feedback_id']}",
            json={"status": "resolved", "admin_reply": "已补充休息区巡查。"},
        )
    )

    assert created.status_code == 201
    assert repeated.json()["feedback_id"] == created.json()["feedback_id"]
    assert "contact" not in visitor_list.json()["feedback"][0]
    assert admin_list.json()["feedback"][0]["contact"] == "visitor@example.com"
    assert updated.json()["status"] == "resolved"


def test_feedback_api_validates_content_and_visitor_routes_exist(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path), seed_attractions=False, seed_foods=False)
    invalid = asyncio.run(
        request(
            app,
            "POST",
            "/api/visitor/feedback",
            json={
                "visitor_id": "visitor_alpha",
                "request_id": "request_1",
                "rating": 6,
                "category": "unknown",
                "content": "太短",
                "contact": "",
            },
        )
    )
    food_page = asyncio.run(request(app, "GET", "/visitor/food"))
    feedback_page = asyncio.run(request(app, "GET", "/visitor/feedback"))

    assert invalid.status_code == 422
    assert food_page.status_code == 200
    assert feedback_page.status_code == 200
