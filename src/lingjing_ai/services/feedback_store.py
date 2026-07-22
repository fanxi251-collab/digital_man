from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import uuid

from psycopg.errors import UniqueViolation

from lingjing_ai.storage.postgres import Row, execute_statements, fetchall, fetchone, schema_connection


@dataclass(frozen=True)
class FeedbackRecord:
    feedback_id: str
    visitor_id: str
    request_id: str
    rating: int
    category: str
    content: str
    contact: str
    status: str
    admin_reply: str
    created_at: str
    updated_at: str


class FeedbackStore:
    def __init__(self, dsn: str, schema: str = "feedback") -> None:
        self.dsn = dsn
        self.schema = schema
        self._init_schema()

    def create_feedback(self, payload: dict[str, Any]) -> FeedbackRecord:
        values = _normalized_payload(payload)
        existing = self._fetchone(
            "SELECT * FROM visitor_feedback WHERE visitor_id = %s AND request_id = %s",
            (values["visitor_id"], values["request_id"]),
        )
        if existing is not None:
            # 网络重试复用原记录，防止游客误以为一次提交产生了多条反馈。
            return _record_from_row(existing)
        feedback_id = f"fb_{uuid.uuid4().hex}"
        now = _utc_now()
        try:
            with schema_connection(self.dsn, self.schema) as conn:
                conn.execute(
                    """
                    INSERT INTO visitor_feedback (
                        feedback_id, visitor_id, request_id, rating, category, content,
                        contact, status, admin_reply, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', '', %s, %s)
                    """,
                    (
                        feedback_id,
                        values["visitor_id"],
                        values["request_id"],
                        values["rating"],
                        values["category"],
                        values["content"],
                        values["contact"],
                        now,
                        now,
                    ),
                )
        except UniqueViolation:
            # 唯一约束赢得并发竞争时读取胜者，让同时重试也获得同一反馈编号。
            winner = self._fetchone(
                "SELECT * FROM visitor_feedback WHERE visitor_id = %s AND request_id = %s",
                (values["visitor_id"], values["request_id"]),
            )
            if winner is None:
                raise
            return _record_from_row(winner)
        return self.get_feedback(feedback_id)

    def get_feedback(self, feedback_id: str) -> FeedbackRecord | None:
        row = self._fetchone("SELECT * FROM visitor_feedback WHERE feedback_id = %s", (feedback_id,))
        return _record_from_row(row) if row else None

    def list_for_visitor(self, visitor_id: str) -> list[FeedbackRecord]:
        rows = self._fetchall(
            """
            SELECT * FROM visitor_feedback WHERE visitor_id = %s
            ORDER BY created_at DESC, feedback_id DESC
            """,
            (str(visitor_id).strip(),),
        )
        return [_record_from_row(row) for row in rows]

    def list_feedback(
        self,
        q: str = "",
        status: str = "",
        category: str = "",
        rating: int | None = None,
    ) -> list[FeedbackRecord]:
        conditions: list[str] = []
        params: list[Any] = []
        if q.strip():
            conditions.append("(content LIKE %s OR contact LIKE %s OR feedback_id LIKE %s)")
            pattern = f"%{q.strip()}%"
            params.extend([pattern, pattern, pattern])
        for column, value in (("status", status), ("category", category)):
            if value.strip():
                conditions.append(f"{column} = %s")
                params.append(value.strip())
        if rating is not None:
            conditions.append("rating = %s")
            params.append(int(rating))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._fetchall(
            f"SELECT * FROM visitor_feedback {where} ORDER BY created_at DESC, feedback_id DESC",
            tuple(params),
        )
        return [_record_from_row(row) for row in rows]

    def update_feedback(self, feedback_id: str, status: str, admin_reply: str) -> FeedbackRecord | None:
        with schema_connection(self.dsn, self.schema) as conn:
            cursor = conn.execute(
                """
                UPDATE visitor_feedback SET status = %s, admin_reply = %s, updated_at = %s
                WHERE feedback_id = %s
                """,
                (str(status).strip(), str(admin_reply).strip(), _utc_now(), feedback_id),
            )
        return self.get_feedback(feedback_id) if cursor.rowcount else None

    def _init_schema(self) -> None:
        # 唯一索引在数据库层保证幂等，即使两个相同请求并发到达也只保留一条。
        execute_statements(
            self.dsn,
            self.schema,
            [
                """
                CREATE TABLE IF NOT EXISTS visitor_feedback (
                    feedback_id TEXT PRIMARY KEY,
                    visitor_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    rating INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    contact TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    admin_reply TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(visitor_id, request_id)
                )
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_feedback_admin_queue
                    ON visitor_feedback(status, created_at DESC)
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_feedback_visitor_history
                    ON visitor_feedback(visitor_id, created_at DESC)
                """,
            ],
        )

    def _fetchone(self, query: str, params: tuple[Any, ...]) -> Row | None:
        return fetchone(self.dsn, self.schema, query, params)

    def _fetchall(self, query: str, params: tuple[Any, ...]) -> list[Row]:
        return fetchall(self.dsn, self.schema, query, params)


def _normalized_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "visitor_id": str(payload.get("visitor_id", "")).strip(),
        "request_id": str(payload.get("request_id", "")).strip(),
        "rating": int(payload.get("rating", 0)),
        "category": str(payload.get("category", "")).strip(),
        "content": str(payload.get("content", "")).strip(),
        "contact": str(payload.get("contact", "")).strip(),
    }


def _record_from_row(row: Row) -> FeedbackRecord:
    return FeedbackRecord(
        feedback_id=str(row["feedback_id"]),
        visitor_id=str(row["visitor_id"]),
        request_id=str(row["request_id"]),
        rating=int(row["rating"]),
        category=str(row["category"]),
        content=str(row["content"]),
        contact=str(row["contact"]),
        status=str(row["status"]),
        admin_reply=str(row["admin_reply"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
