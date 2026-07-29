from pathlib import Path

from lingjing_ai.config.settings import AppSettings
from lingjing_ai.models.rag import SourceChunk
from lingjing_ai.rag.embeddings import HashingEmbeddingProvider
from lingjing_ai.rag.pipeline import RagPipeline
from lingjing_ai.services.conversation import ConversationMessage, build_conversation_context
from lingjing_ai.storage.vector_store import JsonVectorStore


class FakeJsonCache:
    def __init__(self) -> None:
        self.values: dict[str, dict] = {}
        self.set_calls = 0

    def get_json(self, key: str):
        return self.values.get(key)

    def set_json(self, key: str, value: dict, ttl_seconds: int) -> None:
        self.set_calls += 1
        self.values[key] = value

    def clear_prefix(self, prefix: str = "") -> None:
        self.values.clear()


class CountingAnswerGenerator:
    refusal = "当前资料中没有查到可靠依据，暂时无法回答这个问题。"

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, question: str, sources: list[SourceChunk]) -> str:
        self.calls += 1
        if not sources:
            return self.refusal
        return f"第 {self.calls} 次回答：{sources[0].content}"


def build_pipeline(tmp_path: Path, generator: CountingAnswerGenerator) -> RagPipeline:
    settings = AppSettings.for_workspace(tmp_path)
    return RagPipeline(
        settings=settings,
        embedding_provider=HashingEmbeddingProvider(dimensions=64),
        vector_store=JsonVectorStore(tmp_path / "vectors.json"),
        answer_generator=generator,
    )


def test_pipeline_reuses_evidence_search_cache_until_invalidated(tmp_path: Path):
    from lingjing_ai.rag.cache import evidence_search_cache_key

    generator = CountingAnswerGenerator()
    pipeline = build_pipeline(tmp_path, generator)
    pipeline.ingest_text("灵境山资料.md", "灵境山以云海日出和古栈道闻名。")

    first = pipeline.search_sources("灵境山有什么特色")
    second = pipeline.search_sources("灵境山有什么特色")
    assert [source.chunk_id for source in first] == [source.chunk_id for source in second]
    cache_key = evidence_search_cache_key(
        "灵境山有什么特色",
        pipeline.knowledge_version,
        pipeline.settings.retrieval_mode,
        pipeline.settings.top_k,
    )
    assert pipeline.evidence_search_cache.get(cache_key) is not None

    pipeline.invalidate_answer_cache()
    assert pipeline.evidence_search_cache.get(cache_key) is None


def test_pipeline_reuses_answer_cache_for_normalized_question(tmp_path: Path):
    generator = CountingAnswerGenerator()
    pipeline = build_pipeline(tmp_path, generator)
    pipeline.ingest_text("灵境山资料.md", "灵境山以云海日出和古栈道闻名。")

    first = pipeline.ask(" 灵境山有什么特色？ ")
    second = pipeline.ask("灵境山有什么特色")

    assert first.answer == second.answer
    assert generator.calls == 1


def test_pipeline_invalidates_answer_cache_after_upload(tmp_path: Path):
    generator = CountingAnswerGenerator()
    pipeline = build_pipeline(tmp_path, generator)
    pipeline.ingest_text("游客服务.md", "游客服务中心提供婴儿车租赁。")

    first = pipeline.ask("哪里可以租婴儿车？")
    pipeline.ingest_uploaded_text("游客服务更新.md", "游客服务中心提供婴儿车租赁和失物招领服务。")
    second = pipeline.ask("哪里可以租婴儿车？")

    assert first.answer != second.answer
    assert generator.calls == 2


def test_pipeline_cache_uses_standalone_question_from_conversation_context(tmp_path: Path):
    generator = CountingAnswerGenerator()
    pipeline = build_pipeline(tmp_path, generator)
    pipeline.ingest_text("灵山胜境票务.md", "灵山胜境门票包含成人票、老人票和儿童票。")
    context = build_conversation_context(
        "那门票呢？",
        [ConversationMessage(role="user", content="灵山胜境有什么特色？")],
    )

    first = pipeline.ask("那门票呢？", conversation_context=context)
    second = pipeline.ask("灵山胜境门票信息")

    assert first.answer == second.answer
    assert generator.calls == 1


def test_pipeline_reuses_redis_answer_cache_when_available(tmp_path: Path):
    generator = CountingAnswerGenerator()
    redis_cache = FakeJsonCache()
    pipeline = build_pipeline(tmp_path, generator)
    pipeline.answer_cache.redis_cache = redis_cache
    pipeline.ingest_text("灵境山资料.md", "灵境山以云海日出和古栈道闻名。")

    first = pipeline.ask("灵境山有什么特色？")
    second = pipeline.ask("灵境山有什么特色？")

    assert first.answer == second.answer
    assert generator.calls == 1
    assert redis_cache.set_calls == 1


def test_pipeline_falls_back_when_redis_answer_cache_is_unavailable(tmp_path: Path):
    class BrokenJsonCache(FakeJsonCache):
        def get_json(self, key: str):
            raise RuntimeError("redis down")

        def set_json(self, key: str, value: dict, ttl_seconds: int) -> None:
            raise RuntimeError("redis down")

    generator = CountingAnswerGenerator()
    pipeline = build_pipeline(tmp_path, generator)
    pipeline.answer_cache.redis_cache = BrokenJsonCache()
    pipeline.ingest_text("灵境山资料.md", "灵境山以云海日出和古栈道闻名。")

    first = pipeline.ask("灵境山有什么特色？")
    second = pipeline.ask("灵境山有什么特色？")

    assert first.answer == second.answer
    assert generator.calls == 1
