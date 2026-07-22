from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import uuid
from typing import Any

from lingjing_ai.storage.postgres import Row, execute_statements, fetchall, fetchone, schema_connection


MAX_TITLE_CHARS = 40


@dataclass(frozen=True)
class ConversationSessionRecord:
    session_id: str
    visitor_id: str
    title: str
    recent_question: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class StoredChatMessage:
    message_id: int
    session_id: str
    visitor_id: str
    role: str
    content: str
    trace_id: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""


class ConversationStore:
    def __init__(self, dsn: str, schema: str = "conversations") -> None:
        self.dsn = dsn
        self.schema = schema
        self._init_schema()

    def create_session(self, visitor_id: str, first_question: str) -> ConversationSessionRecord:
        visitor_id = _clean_id(visitor_id)
        title = _title_from_question(first_question)
        now = _utc_now()
        session_id = f"sess_{uuid.uuid4().hex}"
        with schema_connection(self.dsn, self.schema) as conn:
            conn.execute(
                """
                INSERT INTO conversation_sessions
                (session_id, visitor_id, title, recent_question, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (session_id, visitor_id, title, first_question.strip(), now, now),
            )
        return ConversationSessionRecord(session_id, visitor_id, title, first_question.strip(), now, now)

    def get_session(self, session_id: str, visitor_id: str) -> ConversationSessionRecord | None:
        row = self._fetchone(
            """
            SELECT session_id, visitor_id, title, recent_question, created_at, updated_at
            FROM conversation_sessions
            WHERE session_id = %s AND visitor_id = %s
            """,
            (session_id, _clean_id(visitor_id)),
        )
        return _session_from_row(row) if row else None

    def list_sessions(self, visitor_id: str) -> list[ConversationSessionRecord]:
        rows = self._fetchall(
            """
            SELECT session_id, visitor_id, title, recent_question, created_at, updated_at
            FROM conversation_sessions
            WHERE visitor_id = %s
            ORDER BY updated_at DESC
            """,
            (_clean_id(visitor_id),),
        )
        return [_session_from_row(row) for row in rows]

    def append_message(
        self,
        session_id: str,
        visitor_id: str,
        role: str,
        content: str,
        trace_id: str = "",
        sources: list[dict[str, Any]] | None = None,
        tool_trace: list[dict[str, Any]] | None = None,
    ) -> StoredChatMessage | None:
        session = self.get_session(session_id, visitor_id)
        if session is None:
            return None
        role = role if role in {"user", "assistant"} else "user"
        content = str(content or "")
        now = _utc_now()
        with schema_connection(self.dsn, self.schema) as conn:
            row = conn.execute(
                """
                INSERT INTO chat_messages
                (session_id, visitor_id, role, content, trace_id, sources_json, tool_trace_json, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING message_id
                """,
                (
                    session_id,
                    _clean_id(visitor_id),
                    role,
                    content,
                    trace_id,
                    json.dumps(sources or [], ensure_ascii=False),
                    json.dumps(tool_trace or [], ensure_ascii=False),
                    now,
                ),
            ).fetchone()
            recent_question = content if role == "user" else session.recent_question
            conn.execute(
                """
                UPDATE conversation_sessions
                SET recent_question = %s, updated_at = %s
                WHERE session_id = %s AND visitor_id = %s
                """,
                (recent_question, now, session_id, _clean_id(visitor_id)),
            )
            message_id = int(row["message_id"])
        return StoredChatMessage(
            message_id=message_id,
            session_id=session_id,
            visitor_id=_clean_id(visitor_id),
            role=role,
            content=content,
            trace_id=trace_id,
            sources=sources or [],
            tool_trace=tool_trace or [],
            created_at=now,
        )

    def append_turn(
        self,
        turn_id: str,
        session_id: str,
        visitor_id: str,
        question: str,
        answer: str,
        trace_id: str = "",
        sources: list[dict[str, Any]] | None = None,
        tool_trace: list[dict[str, Any]] | None = None,
    ) -> bool:
        normalized_visitor = _clean_id(visitor_id)
        now = _utc_now()
        with schema_connection(self.dsn, self.schema) as conn:
            session = conn.execute(
                "SELECT 1 FROM conversation_sessions WHERE session_id = %s AND visitor_id = %s",
                (session_id, normalized_visitor),
            ).fetchone()
            if session is None:
                return False
            marker = conn.execute(
                """
                INSERT INTO completed_realtime_turns
                (turn_id, session_id, visitor_id, created_at) VALUES (%s, %s, %s, %s)
                ON CONFLICT (turn_id) DO NOTHING
                """,
                (turn_id, session_id, normalized_visitor, now),
            )
            if marker.rowcount == 0:
                return False
            # Both messages share one transaction so a retry cannot leave an orphan user message.
            conn.execute(
                """
                INSERT INTO chat_messages
                (session_id, visitor_id, role, content, trace_id, sources_json, tool_trace_json, created_at)
                VALUES (%s, %s, 'user', %s, '', '[]', '[]', %s)
                """,
                (session_id, normalized_visitor, question, now),
            )
            conn.execute(
                """
                INSERT INTO chat_messages
                (session_id, visitor_id, role, content, trace_id, sources_json, tool_trace_json, created_at)
                VALUES (%s, %s, 'assistant', %s, %s, %s, %s, %s)
                """,
                (
                    session_id,
                    normalized_visitor,
                    answer,
                    trace_id,
                    json.dumps(sources or [], ensure_ascii=False),
                    json.dumps(tool_trace or [], ensure_ascii=False),
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE conversation_sessions
                SET recent_question = %s, updated_at = %s
                WHERE session_id = %s AND visitor_id = %s
                """,
                (question, now, session_id, normalized_visitor),
            )
        return True

    def list_messages(self, session_id: str, visitor_id: str) -> list[StoredChatMessage]:
        if self.get_session(session_id, visitor_id) is None:
            return []
        rows = self._fetchall(
            """
            SELECT message_id, session_id, visitor_id, role, content, trace_id,
                   sources_json, tool_trace_json, created_at
            FROM chat_messages
            WHERE session_id = %s AND visitor_id = %s
            ORDER BY message_id ASC
            """,
            (session_id, _clean_id(visitor_id)),
        )
        return [_message_from_row(row) for row in rows]

    def recent_messages(self, session_id: str, visitor_id: str, limit: int = 12) -> list[StoredChatMessage]:
        if self.get_session(session_id, visitor_id) is None:
            return []
        rows = self._fetchall(
            """
            SELECT message_id, session_id, visitor_id, role, content, trace_id,
                   sources_json, tool_trace_json, created_at
            FROM chat_messages
            WHERE session_id = %s AND visitor_id = %s
            ORDER BY message_id DESC
            LIMIT %s
            """,
            (session_id, _clean_id(visitor_id), max(1, int(limit))),
        )
        return [_message_from_row(row) for row in reversed(rows)]

    def delete_session(self, session_id: str, visitor_id: str) -> bool:
        if self.get_session(session_id, visitor_id) is None:
            return False
        normalized_visitor = _clean_id(visitor_id)
        with schema_connection(self.dsn, self.schema) as conn:
            # 先删除幂等标记，既完整擦除会话数据，也兼容尚未添加级联外键的已迁移表。
            conn.execute(
                "DELETE FROM completed_realtime_turns WHERE session_id = %s AND visitor_id = %s",
                (session_id, normalized_visitor),
            )
            conn.execute(
                "DELETE FROM chat_messages WHERE session_id = %s AND visitor_id = %s",
                (session_id, normalized_visitor),
            )
            cursor = conn.execute(
                "DELETE FROM conversation_sessions WHERE session_id = %s AND visitor_id = %s",
                (session_id, normalized_visitor),
            )
        return cursor.rowcount > 0

    def _init_schema(self) -> None:
        # These indexes keep anonymous history lookup bounded by visitor/session,
        # because future游客量增长时不能靠全表扫描维持上下文体验。
        execute_statements(
            self.dsn,
            self.schema,
            [
                """
                CREATE TABLE IF NOT EXISTS conversation_sessions (
                    session_id TEXT PRIMARY KEY,
                    visitor_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    recent_question TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    message_id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    visitor_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    trace_id TEXT NOT NULL DEFAULT '',
                    sources_json TEXT NOT NULL DEFAULT '[]',
                    tool_trace_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES conversation_sessions(session_id) ON DELETE CASCADE
                )
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_conversation_sessions_visitor_updated
                    ON conversation_sessions(visitor_id, updated_at DESC)
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session_visitor
                    ON chat_messages(session_id, visitor_id, message_id)
                """,
                """
                CREATE TABLE IF NOT EXISTS completed_realtime_turns (
                    turn_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    visitor_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES conversation_sessions(session_id) ON DELETE CASCADE
                )
                """,
            ],
        )

    def _fetchone(self, query: str, params: tuple[Any, ...]) -> Row | None:
        return fetchone(self.dsn, self.schema, query, params)

    def _fetchall(self, query: str, params: tuple[Any, ...]) -> list[Row]:
        return fetchall(self.dsn, self.schema, query, params)


def _session_from_row(row: Row) -> ConversationSessionRecord:
    return ConversationSessionRecord(
        session_id=str(row["session_id"]),
        visitor_id=str(row["visitor_id"]),
        title=str(row["title"]),
        recent_question=str(row["recent_question"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _message_from_row(row: Row) -> StoredChatMessage:
    return StoredChatMessage(
        message_id=int(row["message_id"]),
        session_id=str(row["session_id"]),
        visitor_id=str(row["visitor_id"]),
        role=str(row["role"]),
        content=str(row["content"]),
        trace_id=str(row["trace_id"]),
        sources=_safe_json_list(str(row["sources_json"])),
        tool_trace=_safe_json_list(str(row["tool_trace_json"])),
        created_at=str(row["created_at"]),
    )


def _safe_json_list(raw: str) -> list[dict[str, Any]]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def _title_from_question(question: str) -> str:
    title = " ".join(str(question or "").split())
    if len(title) > MAX_TITLE_CHARS:
        return title[:MAX_TITLE_CHARS].rstrip() + "..."
    return title or "新的会话"


def _clean_id(value: str) -> str:
    return str(value or "").strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
