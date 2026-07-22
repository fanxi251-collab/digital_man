from pathlib import Path

import pytest

pytestmark = pytest.mark.usefixtures("postgres_test_context")

from lingjing_ai.services.food_store import FoodStore


def food_payload(name: str = "灵山蔬食馆", status: str = "published") -> dict:
    return {
        "name": name,
        "summary": f"{name}提供适合游览途中休息的灵山风味。",
        "description": f"{name}的详细餐饮信息。",
        "scope": "inside",
        "category": "素食",
        "taste_tags": ["清淡", "江南"],
        "signature_dishes": ["灵山素面", "素包"],
        "price_level": 2,
        "vegetarian_friendly": True,
        "address": "灵山胜境景区内",
        "opening_hours": "以景区当日公告为准",
        "longitude": 120.101,
        "latitude": 31.426,
        "source_url": "https://www.lingshan.com.cn/",
        "verified_at": "2026-07-19",
        "is_featured": True,
        "sort_order": 10,
        "status": status,
    }


def test_food_store_crud_filters_and_archive(pg_dsn: str, foods_schema: str, tmp_path: Path):
    store = FoodStore(pg_dsn, tmp_path / "images", seed_on_empty=False, schema=foods_schema)
    created = store.create_food(food_payload())
    store.create_food({**food_payload("太湖渔村", "draft"), "scope": "nearby"})

    visible = store.list_foods(
        public_only=True,
        q="蔬食",
        scope="inside",
        category="素食",
        taste="清淡",
        price_level=2,
        vegetarian=True,
        featured=True,
    )

    assert [item.name for item in visible] == ["灵山蔬食馆"]
    assert created.signature_dishes == ["灵山素面", "素包"]
    updated = store.update_food(created.food_id, {**food_payload(), "sort_order": 1})
    assert updated is not None and updated.sort_order == 1
    assert store.archive_food(created.food_id) is True
    assert store.list_foods(public_only=True) == []


def test_food_store_manages_one_cover_and_deletes_only_requested_image(
    pg_dsn: str, foods_schema: str, tmp_path: Path
):
    image_dir = tmp_path / "images"
    store = FoodStore(pg_dsn, image_dir, seed_on_empty=False, schema=foods_schema)
    food = store.create_food(food_payload(status="draft"))
    first_path = image_dir / "first.webp"
    second_path = image_dir / "second.webp"
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")

    first = store.add_image(food.food_id, first_path.name, is_cover=True, sort_order=10)
    second = store.add_image(food.food_id, second_path.name, is_cover=False, sort_order=20)
    promoted = store.update_image(food.food_id, second.image_id, is_cover=True, sort_order=1)
    loaded = store.get_food(food.food_id)

    assert promoted is not None and promoted.is_cover is True
    assert [image.image_id for image in loaded.images if image.is_cover] == [second.image_id]
    deleted = store.delete_image(food.food_id, first.image_id)
    assert deleted is not None
    assert first_path.exists() is False
    assert second_path.exists() is True


def test_empty_food_store_seeds_six_published_recommendations_with_covers(
    pg_dsn: str, foods_schema: str, tmp_path: Path
):
    store = FoodStore(pg_dsn, tmp_path / "images", schema=foods_schema)

    seeded = store.list_foods(public_only=True)

    assert len(seeded) == 6
    assert {item.name for item in seeded} == {
        "灵山蔬食馆",
        "灵山五观堂",
        "灵山精舍餐饮",
        "吉祥食集",
        "太湖渔村（古竹路店）",
        "马山渔家菜馆",
    }
    assert all(item.cover_image_url for item in seeded)
    assert all(item.verified_at == "2026-07-19" for item in seeded)
