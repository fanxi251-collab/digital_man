from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any
import uuid

from lingjing_ai.storage.postgres import Row, execute_statements, fetchall, fetchone, schema_connection


PUBLIC_IMAGE_PREFIX = "/media/attractions/"


@dataclass(frozen=True)
class AttractionImageRecord:
    image_id: str
    attraction_id: str
    relative_path: str
    is_cover: bool = False
    sort_order: int = 0
    created_at: str = ""

    @property
    def url(self) -> str:
        return f"{PUBLIC_IMAGE_PREFIX}{self.relative_path}"


@dataclass(frozen=True)
class AttractionRecord:
    attraction_id: str
    name: str
    summary: str
    description: str
    category: str
    tags: list[str]
    address: str
    opening_hours: str
    suggested_duration_minutes: int
    longitude: float
    latitude: float
    is_featured: bool
    sort_order: int
    status: str
    created_at: str
    updated_at: str
    images: list[AttractionImageRecord] = field(default_factory=list)

    @property
    def cover_image_url(self) -> str:
        cover = next((image for image in self.images if image.is_cover), None)
        return cover.url if cover else ""


class AttractionStore:
    def __init__(
        self,
        dsn: str,
        image_dir: Path,
        seed_on_empty: bool = True,
        schema: str = "attractions",
    ) -> None:
        self.dsn = dsn
        self.schema = schema
        self.image_dir = Path(image_dir)
        self.image_dir.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        if seed_on_empty and self._count_attractions() == 0:
            self._seed_demo_attractions()
        elif seed_on_empty:
            self._sync_active_seed_covers()

    def create_attraction(self, payload: dict[str, Any]) -> AttractionRecord:
        attraction_id = f"attr_{uuid.uuid4().hex}"
        now = _utc_now()
        values = _normalized_payload(payload)
        with schema_connection(self.dsn, self.schema) as conn:
            conn.execute(
                """
                INSERT INTO attractions (
                    attraction_id, name, summary, description, category, tags_json,
                    address, opening_hours, suggested_duration_minutes, longitude,
                    latitude, is_featured, sort_order, status, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    attraction_id,
                    values["name"],
                    values["summary"],
                    values["description"],
                    values["category"],
                    json.dumps(values["tags"], ensure_ascii=False),
                    values["address"],
                    values["opening_hours"],
                    values["suggested_duration_minutes"],
                    values["longitude"],
                    values["latitude"],
                    int(values["is_featured"]),
                    values["sort_order"],
                    values["status"],
                    now,
                    now,
                ),
            )
        return self.get_attraction(attraction_id)

    def update_attraction(self, attraction_id: str, payload: dict[str, Any]) -> AttractionRecord | None:
        if self.get_attraction(attraction_id) is None:
            return None
        values = _normalized_payload(payload)
        with schema_connection(self.dsn, self.schema) as conn:
            conn.execute(
                """
                UPDATE attractions SET
                    name = %s, summary = %s, description = %s, category = %s, tags_json = %s,
                    address = %s, opening_hours = %s, suggested_duration_minutes = %s,
                    longitude = %s, latitude = %s, is_featured = %s, sort_order = %s,
                    status = %s, updated_at = %s
                WHERE attraction_id = %s
                """,
                (
                    values["name"],
                    values["summary"],
                    values["description"],
                    values["category"],
                    json.dumps(values["tags"], ensure_ascii=False),
                    values["address"],
                    values["opening_hours"],
                    values["suggested_duration_minutes"],
                    values["longitude"],
                    values["latitude"],
                    int(values["is_featured"]),
                    values["sort_order"],
                    values["status"],
                    _utc_now(),
                    attraction_id,
                ),
            )
        return self.get_attraction(attraction_id)

    def list_attractions(
        self,
        public_only: bool = False,
        q: str = "",
        category: str = "",
        featured: bool | None = None,
        status: str = "",
    ) -> list[AttractionRecord]:
        conditions: list[str] = []
        params: list[Any] = []
        if public_only:
            conditions.append("status = 'published'")
        elif status:
            conditions.append("status = %s")
            params.append(status)
        if q.strip():
            conditions.append("(name LIKE %s OR summary LIKE %s OR tags_json LIKE %s)")
            pattern = f"%{q.strip()}%"
            params.extend([pattern, pattern, pattern])
        if category.strip():
            conditions.append("category = %s")
            params.append(category.strip())
        if featured is not None:
            conditions.append("is_featured = %s")
            params.append(int(featured))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._fetchall(
            f"""
            SELECT * FROM attractions
            {where}
            ORDER BY is_featured DESC, sort_order ASC, updated_at DESC
            """,
            tuple(params),
        )
        return [self._record_from_row(row) for row in rows]

    def get_attraction(self, attraction_id: str, public_only: bool = False) -> AttractionRecord | None:
        status_clause = " AND status = 'published'" if public_only else ""
        row = self._fetchone(
            f"SELECT * FROM attractions WHERE attraction_id = %s{status_clause}",
            (attraction_id,),
        )
        return self._record_from_row(row) if row else None

    def get_published_attraction_by_name(self, name: str) -> AttractionRecord | None:
        normalized_name = str(name or "").strip()
        if not normalized_name:
            return None
        row = self._fetchone(
            """
            SELECT * FROM attractions
            WHERE name = %s AND status = 'published'
            ORDER BY updated_at DESC, created_at DESC, attraction_id DESC
            LIMIT 1
            """,
            (normalized_name,),
        )
        # Exact published-name lookup prevents draft landmarks or fuzzy matches from entering public routes.
        return self._record_from_row(row) if row else None

    def archive_attraction(self, attraction_id: str) -> bool:
        with schema_connection(self.dsn, self.schema) as conn:
            cursor = conn.execute(
                "UPDATE attractions SET status = 'archived', updated_at = %s WHERE attraction_id = %s",
                (_utc_now(), attraction_id),
            )
        return cursor.rowcount > 0

    def add_image(
        self,
        attraction_id: str,
        relative_path: str,
        is_cover: bool = False,
        sort_order: int = 0,
    ) -> AttractionImageRecord | None:
        if self.get_attraction(attraction_id) is None:
            return None
        image_id = f"img_{uuid.uuid4().hex}"
        now = _utc_now()
        with schema_connection(self.dsn, self.schema) as conn:
            if is_cover:
                # A景点只能有一个封面；先清除旧封面可避免游客端出现不确定的主图。
                conn.execute(
                    "UPDATE attraction_images SET is_cover = 0 WHERE attraction_id = %s",
                    (attraction_id,),
                )
            conn.execute(
                """
                INSERT INTO attraction_images
                (image_id, attraction_id, relative_path, is_cover, sort_order, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (image_id, attraction_id, relative_path, int(is_cover), int(sort_order), now),
            )
        return AttractionImageRecord(image_id, attraction_id, relative_path, is_cover, int(sort_order), now)

    def delete_image(self, attraction_id: str, image_id: str) -> AttractionImageRecord | None:
        row = self._fetchone(
            "SELECT * FROM attraction_images WHERE attraction_id = %s AND image_id = %s",
            (attraction_id, image_id),
        )
        if row is None:
            return None
        image = _image_from_row(row)
        with schema_connection(self.dsn, self.schema) as conn:
            conn.execute(
                "DELETE FROM attraction_images WHERE attraction_id = %s AND image_id = %s",
                (attraction_id, image_id),
            )
        image_path = self.image_dir / image.relative_path
        if image_path.is_file():
            # 每次请求只删除数据库已定位的一张图片，符合明确路径删除约束。
            image_path.unlink()
        return image

    def update_image(
        self,
        attraction_id: str,
        image_id: str,
        is_cover: bool,
        sort_order: int,
    ) -> AttractionImageRecord | None:
        row = self._fetchone(
            "SELECT * FROM attraction_images WHERE attraction_id = %s AND image_id = %s",
            (attraction_id, image_id),
        )
        if row is None:
            return None
        with schema_connection(self.dsn, self.schema) as conn:
            if is_cover:
                # 先取消同景点其他封面，确保更新操作不会制造多封面歧义。
                conn.execute(
                    "UPDATE attraction_images SET is_cover = 0 WHERE attraction_id = %s",
                    (attraction_id,),
                )
            conn.execute(
                """
                UPDATE attraction_images SET is_cover = %s, sort_order = %s
                WHERE attraction_id = %s AND image_id = %s
                """,
                (int(is_cover), int(sort_order), attraction_id, image_id),
            )
        updated = self._fetchone(
            "SELECT * FROM attraction_images WHERE attraction_id = %s AND image_id = %s",
            (attraction_id, image_id),
        )
        return _image_from_row(updated) if updated else None

    def has_cover(self, attraction_id: str) -> bool:
        row = self._fetchone(
            "SELECT 1 AS present FROM attraction_images WHERE attraction_id = %s AND is_cover = 1 LIMIT 1",
            (attraction_id,),
        )
        return row is not None

    def _record_from_row(self, row: Row) -> AttractionRecord:
        images = self._images_for_attraction(str(row["attraction_id"]))
        return AttractionRecord(
            attraction_id=str(row["attraction_id"]),
            name=str(row["name"]),
            summary=str(row["summary"]),
            description=str(row["description"]),
            category=str(row["category"]),
            tags=list(json.loads(row["tags_json"] or "[]")),
            address=str(row["address"]),
            opening_hours=str(row["opening_hours"]),
            suggested_duration_minutes=int(row["suggested_duration_minutes"]),
            longitude=float(row["longitude"]),
            latitude=float(row["latitude"]),
            is_featured=bool(row["is_featured"]),
            sort_order=int(row["sort_order"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            images=images,
        )

    def _images_for_attraction(self, attraction_id: str) -> list[AttractionImageRecord]:
        rows = self._fetchall(
            """
            SELECT * FROM attraction_images WHERE attraction_id = %s
            ORDER BY is_cover DESC, sort_order ASC, created_at ASC
            """,
            (attraction_id,),
        )
        return [_image_from_row(row) for row in rows]

    def _init_schema(self) -> None:
        # 索引围绕游客筛选和管理端状态查询建立，避免数据增长后全表扫描。
        execute_statements(
            self.dsn,
            self.schema,
            [
                """
                CREATE TABLE IF NOT EXISTS attractions (
                    attraction_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    address TEXT NOT NULL DEFAULT '',
                    opening_hours TEXT NOT NULL DEFAULT '',
                    suggested_duration_minutes INTEGER NOT NULL DEFAULT 0,
                    longitude DOUBLE PRECISION NOT NULL,
                    latitude DOUBLE PRECISION NOT NULL,
                    is_featured INTEGER NOT NULL DEFAULT 0,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS attraction_images (
                    image_id TEXT PRIMARY KEY,
                    attraction_id TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    is_cover INTEGER NOT NULL DEFAULT 0,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(attraction_id) REFERENCES attractions(attraction_id)
                )
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_attractions_public_order
                    ON attractions(status, is_featured DESC, sort_order ASC)
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_attraction_images_owner_order
                    ON attraction_images(attraction_id, is_cover DESC, sort_order ASC)
                """,
            ],
        )

    def _seed_demo_attractions(self) -> None:
        for index, payload in enumerate(_demo_payloads(), start=1):
            filename = f"seed-{index}.webp"
            source_image = _seed_asset_dir() / filename
            target_image = self.image_dir / filename
            if source_image.is_file() and not target_image.exists():
                # 每张种子图单独复制到运行数据目录，保证首次启动离线可展示且不覆盖管理员文件。
                shutil.copyfile(source_image, target_image)
            attraction = self.create_attraction(payload)
            self.add_image(
                attraction.attraction_id,
                filename,
                is_cover=True,
                sort_order=0,
            )

    def _sync_active_seed_covers(self) -> None:
        """Refresh repository-managed covers without touching administrator uploads."""
        for index in range(1, len(_demo_payloads()) + 1):
            filename = f"seed-{index}.webp"
            active_seed = self._fetchone(
                """
                SELECT 1 AS present FROM attraction_images
                WHERE relative_path = %s AND is_cover = 1
                LIMIT 1
                """,
                (filename,),
            )
            if active_seed is None:
                continue
            source_image = _seed_asset_dir() / filename
            if source_image.is_file():
                shutil.copyfile(source_image, self.image_dir / filename)

    def _count_attractions(self) -> int:
        row = self._fetchone("SELECT COUNT(*) AS count FROM attractions", ())
        return int(row["count"]) if row else 0

    def _fetchone(self, query: str, params: tuple[Any, ...]) -> Row | None:
        return fetchone(self.dsn, self.schema, query, params)

    def _fetchall(self, query: str, params: tuple[Any, ...]) -> list[Row]:
        return fetchall(self.dsn, self.schema, query, params)


def _normalized_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(payload.get("name", "")).strip(),
        "summary": str(payload.get("summary", "")).strip(),
        "description": str(payload.get("description", "")).strip(),
        "category": str(payload.get("category", "")).strip(),
        "tags": [str(tag).strip() for tag in payload.get("tags", []) if str(tag).strip()],
        "address": str(payload.get("address", "")).strip(),
        "opening_hours": str(payload.get("opening_hours", "")).strip(),
        "suggested_duration_minutes": int(payload.get("suggested_duration_minutes", 0)),
        "longitude": float(payload.get("longitude", 0)),
        "latitude": float(payload.get("latitude", 0)),
        "is_featured": bool(payload.get("is_featured", False)),
        "sort_order": int(payload.get("sort_order", 0)),
        "status": str(payload.get("status", "draft")),
    }


def _image_from_row(row: Row) -> AttractionImageRecord:
    return AttractionImageRecord(
        image_id=str(row["image_id"]),
        attraction_id=str(row["attraction_id"]),
        relative_path=str(row["relative_path"]),
        is_cover=bool(row["is_cover"]),
        sort_order=int(row["sort_order"]),
        created_at=str(row["created_at"]),
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_asset_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "attractions"


def _demo_payloads() -> list[dict[str, Any]]:
    names = [
        ("灵山大照壁", "门户景观", 120.102499, 31.421388, "进入灵山胜境的文化序章，适合拍摄太湖与照壁同框画面。"),
        ("五明桥", "人文建筑", 120.102248, 31.421749, "五座石桥横跨香水海，象征佛教文化中的五种智慧。"),
        ("佛足坛", "祈福体验", 120.101497, 31.422725, "位于景区中轴线上的朝圣节点，承载吉祥祈福寓意。"),
        ("五智门", "人文建筑", 120.101292, 31.423055, "汉白玉牌坊气势庄严，是进入核心游览区的重要标志。"),
        ("九龙灌浴", "演艺体验", 120.099984, 31.424601, "以佛祖诞生故事为主题的动态水景与音乐表演。"),
        ("灵山大佛", "核心景观", 120.096477, 31.430194, "灵山胜境代表性地标，可在核心观景区瞻礼、祈福和远眺。"),
        ("灵山梵宫", "室内场馆", 120.102420, 31.428218, "融合佛教艺术、建筑装饰和文化展陈的室内文化空间。"),
        ("五印坛城", "人文建筑", 120.103054, 31.424676, "以藏传佛教文化与坛城建筑意象为特色的深度游览节点。"),
    ]
    return [
        {
            "name": name,
            "summary": summary,
            "description": f"{summary} 游览时请尊重宗教场所礼仪，开放安排以景区当日公告为准。",
            "category": category,
            "tags": ["灵山胜境", "文化", "打卡"],
            "address": f"江苏省无锡市滨湖区灵山胜境景区内·{name}",
            "opening_hours": "以景区当日公告为准",
            "suggested_duration_minutes": 45 if name not in {"灵山梵宫", "灵山大佛"} else 60,
            "longitude": longitude,
            "latitude": latitude,
            "is_featured": name in {"灵山大佛", "九龙灌浴", "灵山梵宫", "五印坛城"},
            "sort_order": index * 10,
            "status": "published",
        }
        for index, (name, category, longitude, latitude, summary) in enumerate(names, start=1)
    ]
