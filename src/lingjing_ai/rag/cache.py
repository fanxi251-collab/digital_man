from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import re
import time

from lingjing_ai.models.rag import RagAnswer
from lingjing_ai.models.rag import SourceChunk
from lingjing_ai.services.redis_cache import RedisJsonCache


@dataclass(frozen=True)
class CachedAnswer:
    answer: RagAnswer
    expires_at: float


@dataclass(frozen=True)
class CachedSources:
    sources: list[SourceChunk]
    expires_at: float


class QuestionCache:
    def __init__(self, max_items: int, ttl_seconds: int) -> None:
        self.max_items = max_items
        self.ttl_seconds = ttl_seconds
        self._items: OrderedDict[str, CachedAnswer] = OrderedDict()

    def get(self, key: str) -> RagAnswer | None:
        item = self._items.get(key)
        if item is None:
            return None
        if item.expires_at < time.time():
            self._items.pop(key, None)
            return None
        self._items.move_to_end(key)
        return item.answer

    def set(self, key: str, answer: RagAnswer) -> None:
        if self.max_items <= 0 or self.ttl_seconds <= 0:
            return
        self._items[key] = CachedAnswer(answer=answer, expires_at=time.time() + self.ttl_seconds)
        self._items.move_to_end(key)
        while len(self._items) > self.max_items:
            self._items.popitem(last=False)

    def clear(self) -> None:
        self._items.clear()


class SourceSearchCache:
    """进程内检索结果短缓存，避免重复问句反复打 embedding / Qdrant。"""

    def __init__(self, max_items: int, ttl_seconds: int) -> None:
        self.max_items = max_items
        self.ttl_seconds = ttl_seconds
        self._items: OrderedDict[str, CachedSources] = OrderedDict()

    def get(self, key: str) -> list[SourceChunk] | None:
        item = self._items.get(key)
        if item is None:
            return None
        if item.expires_at < time.time():
            self._items.pop(key, None)
            return None
        self._items.move_to_end(key)
        return list(item.sources)

    def set(self, key: str, sources: list[SourceChunk]) -> None:
        if self.max_items <= 0 or self.ttl_seconds <= 0:
            return
        self._items[key] = CachedSources(
            sources=list(sources),
            expires_at=time.time() + self.ttl_seconds,
        )
        self._items.move_to_end(key)
        while len(self._items) > self.max_items:
            self._items.popitem(last=False)

    def clear(self) -> None:
        self._items.clear()


def evidence_search_cache_key(
    question: str,
    knowledge_version: str,
    retrieval_mode: str,
    top_k: int,
) -> str:
    return f"evidence|{answer_cache_key(question, knowledge_version, retrieval_mode, top_k)}"


class RedisBackedQuestionCache:
    def __init__(self, memory_cache: QuestionCache, redis_cache: RedisJsonCache | None, ttl_seconds: int) -> None:
        self.memory_cache = memory_cache
        self.redis_cache = redis_cache
        self.ttl_seconds = ttl_seconds

    def get(self, key: str) -> RagAnswer | None:
        cached = self.memory_cache.get(key)
        if cached is not None:
            return cached
        payload = self._get_redis_payload(key)
        if payload is None:
            return None
        answer = _answer_from_payload(payload)
        if answer is None:
            return None
        self.memory_cache.set(key, answer)
        return answer

    def set(self, key: str, answer: RagAnswer) -> None:
        self.memory_cache.set(key, answer)
        if self.redis_cache is not None:
            try:
                self.redis_cache.set_json(f"answer:{key}", _answer_to_payload(answer), self.ttl_seconds)
            except Exception:
                return

    def clear(self) -> None:
        self.memory_cache.clear()
        if self.redis_cache is not None:
            try:
                self.redis_cache.clear_prefix("answer:")
            except Exception:
                return

    def _get_redis_payload(self, key: str) -> dict | None:
        if self.redis_cache is None:
            return None
        try:
            return self.redis_cache.get_json(f"answer:{key}")
        except Exception:
            return None


def _answer_to_payload(answer: RagAnswer) -> dict:
    return {
        "answer": answer.answer,
        "sources": [
            {
                "chunk_id": source.chunk_id,
                "document_id": source.document_id,
                "document_name": source.document_name,
                "content": source.content,
                "score": source.score,
                "metadata": source.metadata,
            }
            for source in answer.sources
        ],
        "confidence": answer.confidence,
        "is_answered": answer.is_answered,
        "trace_id": answer.trace_id,
        "needs_clarification": answer.needs_clarification,
        "clarifying_question": answer.clarifying_question,
    }


def _answer_from_payload(payload: dict) -> RagAnswer | None:
    try:
        return RagAnswer(
            answer=str(payload.get("answer", "")),
            sources=[
                SourceChunk(
                    chunk_id=str(source.get("chunk_id", "")),
                    document_id=str(source.get("document_id", "")),
                    document_name=str(source.get("document_name", "")),
                    content=str(source.get("content", "")),
                    score=float(source.get("score", 0.0)),
                    metadata=dict(source.get("metadata") or {}),
                )
                for source in payload.get("sources", [])
                if isinstance(source, dict)
            ],
            confidence=float(payload.get("confidence", 0.0)),
            is_answered=bool(payload.get("is_answered")),
            trace_id=str(payload.get("trace_id", "")),
            needs_clarification=bool(payload.get("needs_clarification", False)),
            clarifying_question=str(payload.get("clarifying_question", "")),
        )
    except (TypeError, ValueError):
        return None


def normalize_question(question: str) -> str:
    normalized = question.strip().lower()
    normalized = normalized.translate(str.maketrans({"？": "?", "。": ".", "：": ":", "；": ";", "！": "!"}))
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.rstrip("?.:;!，,、 ")


def answer_cache_key(question: str, knowledge_version: str, retrieval_mode: str, top_k: int) -> str:
    return f"{knowledge_version}|{retrieval_mode}|{top_k}|{normalize_question(question)}"
