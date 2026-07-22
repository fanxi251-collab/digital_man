from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any
import uuid

from lingjing_ai.storage.postgres import Row, execute_statements, fetchall, fetchone, schema_connection


PUBLIC_IMAGE_PREFIX = "/media/foods/"


@dataclass(frozen=True)
class FoodImageRecord:
    image_id: str
    food_id: str
    relative_path: str
    is_cover: bool = False
    sort_order: int = 0
    created_at: str = ""

    @property
    def url(self) -> str:
        return f"{PUBLIC_IMAGE_PREFIX}{self.relative_path}"


@dataclass(frozen=True)
class FoodRecord:
    food_id: str
    name: str
    summary: str
    description: str
    scope: str
    category: str
    taste_tags: list[str]
    signature_dishes: list[str]
    price_level: int
    vegetarian_friendly: bool
    address: str
    opening_hours: str
    longitude: float
    latitude: float
    source_url: str
    verified_at: str
    is_featured: bool
    sort_order: int
    status: str
    created_at: str
    updated_at: str
    images: list[FoodImageRecord] = field(default_factory=list)

    @property
    def cover_image_url(self) -> str:
        cover = next((image for image in self.images if image.is_cover), None)
        return cover.url if cover else ""


class FoodStore:
    def __init__(
        self,
        dsn: str,
        image_dir: Path,
        seed_on_empty: bool = True,
        schema: str = "foods",
    ) -> None:
        self.dsn = dsn
        self.schema = schema
        self.image_dir = Path(image_dir)
        self.image_dir.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        if seed_on_empty and self._count_foods() == 0:
            self._seed_foods()
        elif seed_on_empty:
            self._sync_active_seed_covers()

    def create_food(self, payload: dict[str, Any]) -> FoodRecord:
        food_id = f"food_{uuid.uuid4().hex}"
        now = _utc_now()
        values = _normalized_payload(payload)
        with schema_connection(self.dsn, self.schema) as conn:
            conn.execute(
                """
                INSERT INTO foods (
                    food_id, name, summary, description, scope, category,
                    taste_tags_json, signature_dishes_json, price_level,
                    vegetarian_friendly, address, opening_hours, longitude, latitude,
                    source_url, verified_at, is_featured, sort_order, status,
                    created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                _food_values(food_id, values, now, now),
            )
        return self.get_food(food_id)

    def update_food(self, food_id: str, payload: dict[str, Any]) -> FoodRecord | None:
        if self.get_food(food_id) is None:
            return None
        values = _normalized_payload(payload)
        with schema_connection(self.dsn, self.schema) as conn:
            conn.execute(
                """
                UPDATE foods SET
                    name = %s, summary = %s, description = %s, scope = %s, category = %s,
                    taste_tags_json = %s, signature_dishes_json = %s, price_level = %s,
                    vegetarian_friendly = %s, address = %s, opening_hours = %s,
                    longitude = %s, latitude = %s, source_url = %s, verified_at = %s,
                    is_featured = %s, sort_order = %s, status = %s, updated_at = %s
                WHERE food_id = %s
                """,
                _food_update_values(values, _utc_now(), food_id),
            )
        return self.get_food(food_id)

    def list_foods(
        self,
        public_only: bool = False,
        q: str = "",
        scope: str = "",
        category: str = "",
        taste: str = "",
        price_level: int | None = None,
        vegetarian: bool | None = None,
        featured: bool | None = None,
        status: str = "",
    ) -> list[FoodRecord]:
        conditions: list[str] = []
        params: list[Any] = []
        if public_only:
            conditions.append("status = 'published'")
        elif status:
            conditions.append("status = %s")
            params.append(status)
        if q.strip():
            pattern = f"%{q.strip()}%"
            conditions.append(
                "(name LIKE %s OR summary LIKE %s OR taste_tags_json LIKE %s OR signature_dishes_json LIKE %s)"
            )
            params.extend([pattern, pattern, pattern, pattern])
        for column, value in (("scope", scope), ("category", category)):
            if value.strip():
                conditions.append(f"{column} = %s")
                params.append(value.strip())
        if taste.strip():
            conditions.append("taste_tags_json LIKE %s")
            params.append(f"%{taste.strip()}%")
        if price_level is not None:
            conditions.append("price_level = %s")
            params.append(int(price_level))
        if vegetarian is not None:
            conditions.append("vegetarian_friendly = %s")
            params.append(int(vegetarian))
        if featured is not None:
            conditions.append("is_featured = %s")
            params.append(int(featured))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._fetchall(
            f"""
            SELECT * FROM foods
            {where}
            ORDER BY is_featured DESC, sort_order ASC, updated_at DESC
            """,
            tuple(params),
        )
        return [self._record_from_row(row) for row in rows]

    def get_food(self, food_id: str, public_only: bool = False) -> FoodRecord | None:
        status_clause = " AND status = 'published'" if public_only else ""
        row = self._fetchone(
            f"SELECT * FROM foods WHERE food_id = %s{status_clause}",
            (food_id,),
        )
        return self._record_from_row(row) if row else None

    def archive_food(self, food_id: str) -> bool:
        with schema_connection(self.dsn, self.schema) as conn:
            cursor = conn.execute(
                "UPDATE foods SET status = 'archived', updated_at = %s WHERE food_id = %s",
                (_utc_now(), food_id),
            )
        return cursor.rowcount > 0

    def add_image(
        self,
        food_id: str,
        relative_path: str,
        is_cover: bool = False,
        sort_order: int = 0,
    ) -> FoodImageRecord | None:
        if self.get_food(food_id) is None:
            return None
        image_id = f"food_img_{uuid.uuid4().hex}"
        now = _utc_now()
        with schema_connection(self.dsn, self.schema) as conn:
            if is_cover:
                # 每个餐饮地点只保留一个封面，避免游客卡片主图不确定。
                conn.execute("UPDATE food_images SET is_cover = 0 WHERE food_id = %s", (food_id,))
            conn.execute(
                """
                INSERT INTO food_images
                (image_id, food_id, relative_path, is_cover, sort_order, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (image_id, food_id, relative_path, int(is_cover), int(sort_order), now),
            )
        return FoodImageRecord(image_id, food_id, relative_path, is_cover, int(sort_order), now)

    def update_image(
        self,
        food_id: str,
        image_id: str,
        is_cover: bool,
        sort_order: int,
    ) -> FoodImageRecord | None:
        row = self._fetchone(
            "SELECT * FROM food_images WHERE food_id = %s AND image_id = %s",
            (food_id, image_id),
        )
        if row is None:
            return None
        with schema_connection(self.dsn, self.schema) as conn:
            if is_cover:
                conn.execute("UPDATE food_images SET is_cover = 0 WHERE food_id = %s", (food_id,))
            conn.execute(
                """
                UPDATE food_images SET is_cover = %s, sort_order = %s
                WHERE food_id = %s AND image_id = %s
                """,
                (int(is_cover), int(sort_order), food_id, image_id),
            )
        updated = self._fetchone(
            "SELECT * FROM food_images WHERE food_id = %s AND image_id = %s",
            (food_id, image_id),
        )
        return _image_from_row(updated) if updated else None

    def delete_image(self, food_id: str, image_id: str) -> FoodImageRecord | None:
        row = self._fetchone(
            "SELECT * FROM food_images WHERE food_id = %s AND image_id = %s",
            (food_id, image_id),
        )
        if row is None:
            return None
        image = _image_from_row(row)
        with schema_connection(self.dsn, self.schema) as conn:
            conn.execute(
                "DELETE FROM food_images WHERE food_id = %s AND image_id = %s",
                (food_id, image_id),
            )
        image_path = self.image_dir / image.relative_path
        if image_path.is_file():
            # 只删除数据库精确定位的一张文件，避免图片管理影响其他素材。
            image_path.unlink()
        return image

    def has_cover(self, food_id: str) -> bool:
        row = self._fetchone(
            "SELECT 1 AS present FROM food_images WHERE food_id = %s AND is_cover = 1 LIMIT 1",
            (food_id,),
        )
        return row is not None

    def _record_from_row(self, row: Row) -> FoodRecord:
        food_id = str(row["food_id"])
        return FoodRecord(
            food_id=food_id,
            name=str(row["name"]),
            summary=str(row["summary"]),
            description=str(row["description"]),
            scope=str(row["scope"]),
            category=str(row["category"]),
            taste_tags=list(json.loads(row["taste_tags_json"] or "[]")),
            signature_dishes=list(json.loads(row["signature_dishes_json"] or "[]")),
            price_level=int(row["price_level"]),
            vegetarian_friendly=bool(row["vegetarian_friendly"]),
            address=str(row["address"]),
            opening_hours=str(row["opening_hours"]),
            longitude=float(row["longitude"]),
            latitude=float(row["latitude"]),
            source_url=str(row["source_url"]),
            verified_at=str(row["verified_at"]),
            is_featured=bool(row["is_featured"]),
            sort_order=int(row["sort_order"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            images=self._images_for_food(food_id),
        )

    def _images_for_food(self, food_id: str) -> list[FoodImageRecord]:
        rows = self._fetchall(
            """
            SELECT * FROM food_images WHERE food_id = %s
            ORDER BY is_cover DESC, sort_order ASC, created_at ASC
            """,
            (food_id,),
        )
        return [_image_from_row(row) for row in rows]

    def _init_schema(self) -> None:
        # 索引围绕游客筛选与管理状态建立，使内容增长后仍保持即时筛选。
        execute_statements(
            self.dsn,
            self.schema,
            [
                """
                CREATE TABLE IF NOT EXISTS foods (
                    food_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    description TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    category TEXT NOT NULL,
                    taste_tags_json TEXT NOT NULL DEFAULT '[]',
                    signature_dishes_json TEXT NOT NULL DEFAULT '[]',
                    price_level INTEGER NOT NULL,
                    vegetarian_friendly INTEGER NOT NULL DEFAULT 0,
                    address TEXT NOT NULL,
                    opening_hours TEXT NOT NULL,
                    longitude DOUBLE PRECISION NOT NULL,
                    latitude DOUBLE PRECISION NOT NULL,
                    source_url TEXT NOT NULL DEFAULT '',
                    verified_at TEXT NOT NULL DEFAULT '',
                    is_featured INTEGER NOT NULL DEFAULT 0,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS food_images (
                    image_id TEXT PRIMARY KEY,
                    food_id TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    is_cover INTEGER NOT NULL DEFAULT 0,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(food_id) REFERENCES foods(food_id)
                )
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_foods_public_order
                    ON foods(status, is_featured DESC, sort_order ASC)
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_food_images_owner_order
                    ON food_images(food_id, is_cover DESC, sort_order ASC)
                """,
            ],
        )

    def _seed_foods(self) -> None:
        for index, payload in enumerate(_seed_payloads(), start=1):
            filename = f"seed-{index}.webp"
            source = _seed_asset_dir() / filename
            if not source.is_file():
                continue
            target = self.image_dir / filename
            if not target.exists():
                shutil.copyfile(source, target)
            food = self.create_food(payload)
            self.add_image(food.food_id, filename, is_cover=True)

    def _sync_active_seed_covers(self) -> None:
        for index in range(1, len(_seed_payloads()) + 1):
            filename = f"seed-{index}.webp"
            active = self._fetchone(
                "SELECT 1 AS present FROM food_images WHERE relative_path = %s AND is_cover = 1 LIMIT 1",
                (filename,),
            )
            source = _seed_asset_dir() / filename
            if active is not None and source.is_file():
                shutil.copyfile(source, self.image_dir / filename)

    def _count_foods(self) -> int:
        row = self._fetchone("SELECT COUNT(*) AS count FROM foods", ())
        return int(row["count"]) if row else 0

    def _fetchone(self, query: str, params: tuple[Any, ...]) -> Row | None:
        return fetchone(self.dsn, self.schema, query, params)

    def _fetchall(self, query: str, params: tuple[Any, ...]) -> list[Row]:
        return fetchall(self.dsn, self.schema, query, params)


def _food_values(food_id: str, values: dict[str, Any], created_at: str, updated_at: str) -> tuple[Any, ...]:
    return (
        food_id,
        values["name"], values["summary"], values["description"], values["scope"], values["category"],
        json.dumps(values["taste_tags"], ensure_ascii=False),
        json.dumps(values["signature_dishes"], ensure_ascii=False),
        values["price_level"], int(values["vegetarian_friendly"]), values["address"],
        values["opening_hours"], values["longitude"], values["latitude"], values["source_url"],
        values["verified_at"], int(values["is_featured"]), values["sort_order"], values["status"],
        created_at, updated_at,
    )


def _food_update_values(values: dict[str, Any], updated_at: str, food_id: str) -> tuple[Any, ...]:
    return _food_values("", values, "", updated_at)[1:-2] + (updated_at, food_id)


def _normalized_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(payload.get("name", "")).strip(),
        "summary": str(payload.get("summary", "")).strip(),
        "description": str(payload.get("description", "")).strip(),
        "scope": str(payload.get("scope", "inside")).strip(),
        "category": str(payload.get("category", "")).strip(),
        "taste_tags": [str(item).strip() for item in payload.get("taste_tags", []) if str(item).strip()],
        "signature_dishes": [str(item).strip() for item in payload.get("signature_dishes", []) if str(item).strip()],
        "price_level": int(payload.get("price_level", 1)),
        "vegetarian_friendly": bool(payload.get("vegetarian_friendly", False)),
        "address": str(payload.get("address", "")).strip(),
        "opening_hours": str(payload.get("opening_hours", "")).strip(),
        "longitude": float(payload.get("longitude", 0)),
        "latitude": float(payload.get("latitude", 0)),
        "source_url": str(payload.get("source_url", "")).strip(),
        "verified_at": str(payload.get("verified_at", "")).strip(),
        "is_featured": bool(payload.get("is_featured", False)),
        "sort_order": int(payload.get("sort_order", 0)),
        "status": str(payload.get("status", "draft")).strip(),
    }


def _image_from_row(row: Row) -> FoodImageRecord:
    return FoodImageRecord(
        image_id=str(row["image_id"]),
        food_id=str(row["food_id"]),
        relative_path=str(row["relative_path"]),
        is_cover=bool(row["is_cover"]),
        sort_order=int(row["sort_order"]),
        created_at=str(row["created_at"]),
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_asset_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "foods"


def _seed_payloads() -> list[dict[str, Any]]:
    source = "https://www.lingshan.com.cn/web/park/introduction/1.html"
    entries = [
        ("灵山蔬食馆", "inside", "素食", ["清淡", "江南"], ["灵山素面", "素包"], 2, True, "景区阿育王柱广场东侧", 120.1017, 31.4260, source),
        ("灵山五观堂", "inside", "素食", ["禅意", "清淡"], ["净素自助餐", "灵山斋"], 3, True, "灵山梵宫三楼", 120.1024, 31.4282, source),
        ("灵山精舍餐饮", "inside", "正餐", ["江南", "精致"], ["禅意精品餐", "时令蔬食"], 4, True, "灵山梵宫东侧", 120.1030, 31.4281, source),
        ("吉祥食集", "inside", "小吃", ["多样", "便捷"], ["灵山福饼", "特色小吃"], 1, True, "灵山胜境景区内", 120.1010, 31.4248, source),
        ("太湖渔村（古竹路店）", "nearby", "正餐", ["鲜美", "江南"], ["太湖白鱼", "银鱼炒蛋"], 3, False, "无锡市滨湖区古竹路附近", 120.1110, 31.4200, "https://maps.apple.com/place?auid=1117271386637773"),
        ("马山渔家菜馆", "nearby", "正餐", ["本帮", "家常"], ["太湖湖鲜", "无锡风味菜"], 2, False, "无锡市滨湖区古竹路36号附近", 120.1090, 31.4190, "https://m.dianping.com/shop/841592060"),
    ]
    return [
        {
            "name": name,
            "summary": f"{name}提供适合灵山旅程的{category}选择。",
            "description": "图片为菜品氛围示意，营业与供应信息请以现场当日公告为准。",
            "scope": scope,
            "category": category,
            "taste_tags": tastes,
            "signature_dishes": dishes,
            "price_level": price,
            "vegetarian_friendly": vegetarian,
            "address": address,
            "opening_hours": "以现场当日信息为准",
            "longitude": longitude,
            "latitude": latitude,
            "source_url": source_url,
            "verified_at": "2026-07-19",
            "is_featured": index <= 4,
            "sort_order": index * 10,
            "status": "published",
        }
        for index, (name, scope, category, tastes, dishes, price, vegetarian, address, longitude, latitude, source_url)
        in enumerate(entries, start=1)
    ]
