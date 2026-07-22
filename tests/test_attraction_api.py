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


def payload(name: str, status: str = "published") -> dict:
    return {
        "name": name,
        "summary": f"{name}简介",
        "description": f"{name}详细介绍",
        "category": "核心景观",
        "tags": ["文化", "打卡"],
        "address": "灵山胜境景区内",
        "opening_hours": "以景区公告为准",
        "suggested_duration_minutes": 45,
        "longitude": 120.09,
        "latitude": 31.42,
        "is_featured": True,
        "sort_order": 1,
        "status": status,
    }


async def request(app, method: str, url: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, url, **kwargs)


def test_admin_crud_and_public_filters(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path), seed_attractions=False)

    created = asyncio.run(request(app, "POST", "/api/admin/attractions", json=payload("灵山大佛", "draft")))
    asyncio.run(request(app, "POST", "/api/admin/attractions", json=payload("五明桥", "draft")))
    attraction_id = created.json()["attraction_id"]
    asyncio.run(
        request(
            app,
            "POST",
            f"/api/admin/attractions/{attraction_id}/images",
            params={"is_cover": "true"},
            files={"file": ("cover.webp", b"RIFF-demo-WEBP", "image/webp")},
        )
    )
    asyncio.run(
        request(
            app,
            "PUT",
            f"/api/admin/attractions/{attraction_id}",
            json=payload("灵山大佛", "published"),
        )
    )
    listing = asyncio.run(
        request(app, "GET", "/api/visitor/attractions", params={"q": "大佛", "featured": "true"})
    )
    updated = asyncio.run(
        request(
            app,
            "PUT",
            f"/api/admin/attractions/{attraction_id}",
            json={**payload("灵山大佛"), "summary": "更新后的简介"},
        )
    )
    archived = asyncio.run(request(app, "DELETE", f"/api/admin/attractions/{attraction_id}"))
    public_after_archive = asyncio.run(request(app, "GET", "/api/visitor/attractions"))

    assert created.status_code == 201
    assert [item["name"] for item in listing.json()["attractions"]] == ["灵山大佛"]
    assert updated.json()["summary"] == "更新后的简介"
    assert archived.status_code == 200
    assert public_after_archive.json()["attractions"] == []


def test_admin_validates_coordinates_and_requires_cover_before_publish(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path), seed_attractions=False)

    invalid = asyncio.run(
        request(app, "POST", "/api/admin/attractions", json={**payload("错误坐标"), "latitude": 100})
    )
    draft = asyncio.run(
        request(app, "POST", "/api/admin/attractions", json=payload("待发布景点", "draft"))
    )
    publish = asyncio.run(
        request(
            app,
            "PUT",
            f"/api/admin/attractions/{draft.json()['attraction_id']}",
            json=payload("待发布景点", "published"),
        )
    )

    assert invalid.status_code == 422
    assert draft.status_code == 201
    assert publish.status_code == 400
    assert "封面" in publish.json()["detail"]


def test_image_upload_rejects_bad_files_and_deletes_one_image(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path), seed_attractions=False)
    draft = asyncio.run(request(app, "POST", "/api/admin/attractions", json=payload("图集景点", "draft")))
    attraction_id = draft.json()["attraction_id"]

    bad = asyncio.run(
        request(
            app,
            "POST",
            f"/api/admin/attractions/{attraction_id}/images",
            files={"file": ("bad.gif", b"GIF89a", "image/gif")},
        )
    )
    first = asyncio.run(
        request(
            app,
            "POST",
            f"/api/admin/attractions/{attraction_id}/images",
            params={"is_cover": "true", "sort_order": 1},
            files={"file": ("cover.webp", b"RIFF-demo-WEBP", "image/webp")},
        )
    )
    second = asyncio.run(
        request(
            app,
            "POST",
            f"/api/admin/attractions/{attraction_id}/images",
            files={"file": ("gallery.png", b"\x89PNG-demo", "image/png")},
        )
    )
    deleted = asyncio.run(
        request(
            app,
            "DELETE",
            f"/api/admin/attractions/{attraction_id}/images/{second.json()['image_id']}",
        )
    )
    detail = asyncio.run(request(app, "GET", f"/api/admin/attractions/{attraction_id}"))

    assert bad.status_code == 400
    assert first.status_code == 201
    assert second.status_code == 201
    assert deleted.status_code == 200
    assert [image["image_id"] for image in detail.json()["images"]] == [first.json()["image_id"]]


def test_admin_can_promote_existing_gallery_image_to_cover(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path), seed_attractions=False)
    draft = asyncio.run(request(app, "POST", "/api/admin/attractions", json=payload("封面设置", "draft")))
    attraction_id = draft.json()["attraction_id"]
    first = asyncio.run(
        request(
            app,
            "POST",
            f"/api/admin/attractions/{attraction_id}/images",
            params={"is_cover": "true"},
            files={"file": ("first.webp", b"RIFF-first-WEBP", "image/webp")},
        )
    )
    second = asyncio.run(
        request(
            app,
            "POST",
            f"/api/admin/attractions/{attraction_id}/images",
            files={"file": ("second.webp", b"RIFF-second-WEBP", "image/webp")},
        )
    )

    promoted = asyncio.run(
        request(
            app,
            "PUT",
            f"/api/admin/attractions/{attraction_id}/images/{second.json()['image_id']}",
            json={"is_cover": True, "sort_order": 2},
        )
    )
    detail = asyncio.run(request(app, "GET", f"/api/admin/attractions/{attraction_id}"))

    assert promoted.status_code == 200
    assert promoted.json()["is_cover"] is True
    covers = [image for image in detail.json()["images"] if image["is_cover"]]
    assert [image["image_id"] for image in covers] == [second.json()["image_id"]]
    assert first.json()["image_id"] != second.json()["image_id"]
