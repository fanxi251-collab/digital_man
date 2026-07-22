from pathlib import Path

import pytest

pytestmark = pytest.mark.usefixtures("postgres_test_context")

from lingjing_ai.services.attraction_store import AttractionStore


def attraction_payload(name: str = "灵山大佛", status: str = "published") -> dict:
    return {
        "name": name,
        "summary": f"{name}是灵山胜境代表景观。",
        "description": f"这里记录{name}的文化内涵与游览建议。",
        "category": "核心景观",
        "tags": ["地标", "文化"],
        "address": "江苏省无锡市滨湖区马山灵山路1号",
        "opening_hours": "以景区当日公告为准",
        "suggested_duration_minutes": 60,
        "longitude": 120.091,
        "latitude": 31.424,
        "is_featured": True,
        "sort_order": 10,
        "status": status,
    }


def test_store_creates_updates_filters_and_archives_attractions(
    pg_dsn: str, attractions_schema: str, tmp_path: Path
):
    store = AttractionStore(
        pg_dsn, tmp_path / "images", seed_on_empty=False, schema=attractions_schema
    )
    created = store.create_attraction(attraction_payload())
    store.create_attraction(attraction_payload("五明桥", status="draft"))

    assert created.name == "灵山大佛"
    assert created.tags == ["地标", "文化"]
    assert [item.name for item in store.list_attractions(public_only=True)] == ["灵山大佛"]
    assert [item.name for item in store.list_attractions(q="大佛", category="核心景观", featured=True)] == [
        "灵山大佛"
    ]

    updated = store.update_attraction(created.attraction_id, {**attraction_payload(), "sort_order": 1})
    assert updated is not None
    assert updated.sort_order == 1
    assert store.archive_attraction(created.attraction_id) is True
    assert store.list_attractions(public_only=True) == []
    assert store.get_attraction(created.attraction_id).status == "archived"


def test_store_finds_latest_published_attraction_by_exact_name(
    pg_dsn: str, attractions_schema: str, tmp_path: Path
):
    store = AttractionStore(
        pg_dsn, tmp_path / "images", seed_on_empty=False, schema=attractions_schema
    )
    published = store.create_attraction(
        {**attraction_payload("五明桥"), "longitude": 120.102248, "latitude": 31.421749}
    )
    store.create_attraction(
        {**attraction_payload("五明桥", status="draft"), "longitude": 1.0, "latitude": 2.0}
    )

    found = store.get_published_attraction_by_name("五明桥")

    assert found is not None
    assert found.attraction_id == published.attraction_id
    assert found.longitude == 120.102248
    assert store.get_published_attraction_by_name("五明") is None
    assert store.get_published_attraction_by_name("不存在景点") is None


def test_store_orders_gallery_and_deletes_only_requested_image(
    pg_dsn: str, attractions_schema: str, tmp_path: Path
):
    image_dir = tmp_path / "images"
    store = AttractionStore(pg_dsn, image_dir, seed_on_empty=False, schema=attractions_schema)
    attraction = store.create_attraction(attraction_payload())
    first_path = image_dir / "first.webp"
    second_path = image_dir / "second.webp"
    image_dir.mkdir(parents=True, exist_ok=True)
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")

    first = store.add_image(attraction.attraction_id, "first.webp", is_cover=False, sort_order=20)
    second = store.add_image(attraction.attraction_id, "second.webp", is_cover=True, sort_order=10)

    loaded = store.get_attraction(attraction.attraction_id)
    assert [image.image_id for image in loaded.images] == [second.image_id, first.image_id]
    assert loaded.cover_image_url.endswith("second.webp")

    deleted = store.delete_image(attraction.attraction_id, first.image_id)
    assert deleted is not None
    assert first_path.exists() is False
    assert second_path.exists() is True
    assert [image.image_id for image in store.get_attraction(attraction.attraction_id).images] == [second.image_id]


def test_empty_store_seeds_eight_attractions_only_once(
    pg_dsn: str, attractions_schema: str, tmp_path: Path
):
    image_dir = tmp_path / "images"

    first = AttractionStore(pg_dsn, image_dir, seed_on_empty=True, schema=attractions_schema)
    seed_path = image_dir / "seed-1.webp"
    expected_seed = seed_path.read_bytes()
    seed_path.write_bytes(b"stale-seed")
    second = AttractionStore(pg_dsn, image_dir, seed_on_empty=True, schema=attractions_schema)

    assert len(first.list_attractions(public_only=True)) == 8
    assert len(second.list_attractions(public_only=True)) == 8
    assert len(list(image_dir.glob("seed-*.webp"))) == 8
    assert seed_path.read_bytes() == expected_seed
    assert {item.name for item in second.list_attractions(public_only=True)} >= {
        "灵山大佛",
        "九龙灌浴",
        "灵山梵宫",
        "五印坛城",
    }


def test_store_does_not_overwrite_seed_after_admin_sets_custom_cover(
    pg_dsn: str, attractions_schema: str, tmp_path: Path
):
    image_dir = tmp_path / "images"
    store = AttractionStore(pg_dsn, image_dir, seed_on_empty=True, schema=attractions_schema)
    attraction = next(item for item in store.list_attractions() if item.sort_order == 10)
    seed_path = image_dir / "seed-1.webp"
    custom_path = image_dir / "custom.webp"
    custom_path.write_bytes(b"custom")
    store.add_image(attraction.attraction_id, custom_path.name, is_cover=True)
    seed_path.write_bytes(b"administrator-kept-copy")

    AttractionStore(pg_dsn, image_dir, seed_on_empty=True, schema=attractions_schema)

    assert seed_path.read_bytes() == b"administrator-kept-copy"
    assert store.get_attraction(attraction.attraction_id).cover_image_url.endswith("custom.webp")
