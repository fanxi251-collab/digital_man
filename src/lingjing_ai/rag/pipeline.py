from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import uuid
from typing import Iterator, Any

from lingjing_ai.config.settings import AppSettings
from lingjing_ai.models.rag import Document, DocumentRecord, RagAnswer, SourceChunk
from lingjing_ai.rag.cache import (
    QuestionCache,
    RedisBackedQuestionCache,
    SourceSearchCache,
    answer_cache_key,
    evidence_search_cache_key,
)
from lingjing_ai.rag.chunker import TextChunker
from lingjing_ai.rag.embeddings import HashingEmbeddingProvider
from lingjing_ai.rag.generator import ExtractiveAnswerGenerator
from lingjing_ai.rag.retriever import HybridRetriever
from lingjing_ai.services.conversation import ConversationContext
from lingjing_ai.services.document_manifest import DocumentManifestStore
from lingjing_ai.services.question_expansion import rank_question_candidates
from lingjing_ai.services.redis_cache import RedisJsonCache
from lingjing_ai.kg.store import DisabledKnowledgeGraphStore, KnowledgeGraphStore
from lingjing_ai.storage.vector_store import VectorStore


class RagPipeline:
    def __init__(
        self,
        settings: AppSettings,
        embedding_provider: HashingEmbeddingProvider,
        vector_store: VectorStore,
        answer_generator: ExtractiveAnswerGenerator,
        knowledge_graph: KnowledgeGraphStore | None = None,
    ) -> None:
        self.settings = settings
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.answer_generator = answer_generator
        self.knowledge_graph = knowledge_graph or DisabledKnowledgeGraphStore()
        self.chunker = TextChunker(settings.chunk_size, settings.chunk_overlap)
        self.retriever = HybridRetriever(
            vector_store=vector_store,
            embedding_provider=embedding_provider,
            vector_top_k=settings.vector_top_k,
            keyword_top_k=settings.keyword_top_k,
            rerank_top_k=settings.rerank_top_k,
            rrf_k=settings.rrf_k,
        )
        self.knowledge_version = uuid.uuid4().hex
        memory_answer_cache = QuestionCache(
            max_items=settings.answer_cache_max_items,
            ttl_seconds=settings.answer_cache_ttl_seconds,
        )
        self.redis_cache = RedisJsonCache.from_url(
            enabled=settings.redis_enabled,
            redis_url=settings.redis_url,
            prefix=settings.redis_cache_prefix,
        )
        self.answer_cache = RedisBackedQuestionCache(
            memory_cache=memory_answer_cache,
            redis_cache=self.redis_cache,
            ttl_seconds=settings.redis_answer_cache_ttl_seconds,
        )
        # 检索层短缓存：资料更新时随 invalidate_answer_cache 一并清空。
        self.evidence_search_cache = SourceSearchCache(
            max_items=settings.evidence_search_cache_max_items,
            ttl_seconds=settings.evidence_search_cache_ttl_seconds,
        )
        self.document_manifest = DocumentManifestStore(
            manifest_path=settings.data_dir / "document_manifest.json",
            uploaded_dir=settings.data_dir / "uploaded",
        )

    def ingest_text(self, document_name: str, text: str) -> Document:
        self._ensure_dirs()
        document_id = self._document_id(document_name)
        document_path = self.settings.data_dir / "processed" / f"{document_id}.txt"
        document_path.parent.mkdir(parents=True, exist_ok=True)
        document_path.write_text(text, encoding="utf-8")
        self._index_text(document_id, document_name, text, {})
        self.invalidate_answer_cache()
        return Document(id=document_id, name=document_name, path=str(document_path))

    def ingest_file(self, source_path: Path) -> Document:
        source = Path(source_path)
        text = source.read_text(encoding="utf-8")
        return self.ingest_uploaded_text(source.name, text)

    def ingest_uploaded_text(self, document_name: str, text: str) -> Document:
        self._ensure_dirs()
        file_md5 = self._text_md5(text)
        document_id = self._document_id_from_md5(document_name, file_md5)
        suffix = Path(document_name).suffix.lower() or ".txt"
        uploaded_path = self.settings.data_dir / "uploaded" / f"{document_id}{suffix}"
        uploaded_path.parent.mkdir(parents=True, exist_ok=True)
        uploaded_path.write_text(text, encoding="utf-8")
        indexed_chunks = self._index_text(document_id, document_name, text, {"file_md5": file_md5})
        self._upsert_document_record(document_id, document_name, uploaded_path, file_md5, indexed_chunks)
        self.invalidate_answer_cache()
        return Document(id=document_id, name=document_name, path=str(uploaded_path))

    def list_documents(self) -> list[DocumentRecord]:
        return self.document_manifest.list_records()

    def get_document_content(self, document_id: str) -> str | None:
        record = self.document_manifest.get(document_id)
        if record is None:
            return None
        path = Path(record.saved_path)
        if not path.is_file() or path.suffix.lower() not in self.settings.allowed_upload_extensions:
            return None
        return path.read_text(encoding="utf-8")

    def reindex_document(self, document_id: str) -> DocumentRecord | None:
        record = self.document_manifest.get(document_id)
        if record is None:
            return None
        path = Path(record.saved_path)
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8")
        file_md5 = self._text_md5(text)
        self.vector_store.delete_document(document_id)
        indexed_chunks = self._index_text(document_id, record.document_name, text, {"file_md5": file_md5})
        updated = self._upsert_document_record(document_id, record.document_name, path, file_md5, indexed_chunks)
        self.invalidate_answer_cache()
        return updated

    def rebuild_index_from_manifest(self) -> int:
        indexed_chunks = 0
        for record in self.document_manifest.list_records():
            path = Path(record.saved_path)
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            file_md5 = self._text_md5(text)
            indexed = self._index_text(record.document_id, record.document_name, text, {"file_md5": file_md5})
            self._upsert_document_record(record.document_id, record.document_name, path, file_md5, indexed)
            indexed_chunks += indexed
        if indexed_chunks:
            self.invalidate_answer_cache()
        return indexed_chunks

    def rebuild_knowledge_graph_from_manifest(self) -> int:
        indexed_chunks = 0
        for record in self.document_manifest.list_records():
            path = Path(record.saved_path)
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            chunks = self.chunker.split(record.document_id, record.document_name, text)
            self.knowledge_graph.clear_document(record.document_id)
            self.knowledge_graph.index_chunks(chunks)
            indexed_chunks += len(chunks)
        if indexed_chunks:
            self.invalidate_answer_cache()
        return indexed_chunks

    def delete_document(self, document_id: str) -> bool:
        record = self.document_manifest.get(document_id)
        if record is None:
            return False
        path = Path(record.saved_path)
        if path.exists() and not self._is_uploaded_file(path):
            return False
        if path.exists():
            path.unlink()
        self.vector_store.delete_document(document_id)
        self.knowledge_graph.delete_document(document_id)
        self.document_manifest.remove(document_id)
        self.invalidate_answer_cache()
        return True

    def _index_text(
        self,
        document_id: str,
        document_name: str,
        text: str,
        metadata: dict[str, str],
    ) -> int:
        chunks = self.chunker.split(document_id, document_name, text)
        records = []
        for chunk in chunks:
            chunk_metadata = {**metadata, **chunk.metadata}
            records.append(
                {
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "document_name": chunk.document_name,
                    "content": chunk.content,
                    "metadata": chunk_metadata,
                    "embedding": self.embedding_provider.embed(chunk.content),
                }
            )
        self.vector_store.upsert(records)
        # Clear first so reindexing the same document updates graph facts instead of duplicating stale edges.
        self.knowledge_graph.clear_document(document_id)
        self.knowledge_graph.index_chunks(chunks)
        return len(records)

    def _upsert_document_record(
        self,
        document_id: str,
        document_name: str,
        saved_path: Path,
        file_md5: str,
        indexed_chunks: int,
    ) -> DocumentRecord:
        existing = self.document_manifest.get(document_id)
        now = datetime.now(timezone.utc).isoformat()
        record = DocumentRecord(
            document_id=document_id,
            document_name=document_name,
            saved_path=str(saved_path),
            file_md5=file_md5,
            file_size=saved_path.stat().st_size,
            indexed_chunks=indexed_chunks,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self.document_manifest.upsert(record)
        return record

    def ask(self, question: str, conversation_context: ConversationContext | None = None) -> RagAnswer:
        if conversation_context and conversation_context.needs_clarification:
            result = RagAnswer(
                answer=conversation_context.clarifying_question,
                sources=[],
                confidence=0.0,
                is_answered=False,
                trace_id=f"qa_{uuid.uuid4().hex}",
                needs_clarification=True,
                clarifying_question=conversation_context.clarifying_question,
            )
            self._write_qa_log(conversation_context.standalone_question, result)
            return result

        active_question = self._active_question(question, conversation_context)
        context_summary = self._context_summary(conversation_context)
        cache_key = self._cache_key(active_question)
        cached = self._get_cached_answer(cache_key)
        if cached is not None:
            return cached

        sources = self.search_sources(active_question)
        answer = self._generate_answer(active_question, sources, context_summary)
        answer = self._apply_assumptions(answer, conversation_context)
        result = self._build_result(answer, sources)
        self._set_cached_answer(cache_key, result)
        self._write_qa_log(active_question, result)
        return result

    def ask_stream(self, question: str, conversation_context: ConversationContext | None = None) -> Iterator[dict[str, Any]]:
        if conversation_context and conversation_context.needs_clarification:
            result = RagAnswer(
                answer=conversation_context.clarifying_question,
                sources=[],
                confidence=0.0,
                is_answered=False,
                trace_id=f"qa_{uuid.uuid4().hex}",
                needs_clarification=True,
                clarifying_question=conversation_context.clarifying_question,
            )
            yield self._meta_event(result)
            for token in self._split_cached_answer(result.answer):
                yield {"type": "token", "content": token}
            self._write_qa_log(conversation_context.standalone_question, result)
            yield {"type": "done", "trace_id": result.trace_id}
            return

        active_question = self._active_question(question, conversation_context)
        context_summary = self._context_summary(conversation_context)
        cache_key = self._cache_key(active_question)
        cached = self._get_cached_answer(cache_key)
        if cached is not None:
            yield self._meta_event(cached)
            for token in self._split_cached_answer(cached.answer):
                yield {"type": "token", "content": token}
            yield {"type": "done", "trace_id": cached.trace_id}
            return

        sources = self.search_sources(active_question)
        result = self._build_result("", sources)
        yield self._meta_event(result)

        if conversation_context and conversation_context.assumptions:
            answer = self._apply_assumptions(
                self._generate_answer(active_question, sources, context_summary),
                conversation_context,
            )
            for token in self._split_cached_answer(answer):
                yield {"type": "token", "content": token}
            final_result = RagAnswer(
                answer=answer,
                sources=sources,
                confidence=result.confidence,
                is_answered=result.is_answered,
                trace_id=result.trace_id,
            )
            self._set_cached_answer(cache_key, final_result)
            self._write_qa_log(active_question, final_result)
            yield {"type": "done", "trace_id": final_result.trace_id}
            return

        answer_parts = []
        stream_method = getattr(self.answer_generator, "generate_stream", None)
        tokens = (
            self._generate_answer_stream(stream_method, active_question, sources, context_summary)
            if stream_method
            else [self._generate_answer(active_question, sources, context_summary)]
        )
        for token in tokens:
            answer_parts.append(token)
            yield {"type": "token", "content": token}
        answer = self._apply_assumptions("".join(answer_parts), conversation_context)

        final_result = RagAnswer(
            answer=answer,
            sources=sources,
            confidence=result.confidence,
            is_answered=result.is_answered,
            trace_id=result.trace_id,
        )
        self._set_cached_answer(cache_key, final_result)
        self._write_qa_log(active_question, final_result)
        yield {"type": "done", "trace_id": final_result.trace_id}

    def invalidate_answer_cache(self) -> None:
        self.knowledge_version = uuid.uuid4().hex
        self.answer_cache.clear()
        self.evidence_search_cache.clear()

    def search_sources(self, question: str) -> list[SourceChunk]:
        cache_key = evidence_search_cache_key(
            question=question,
            knowledge_version=self.knowledge_version,
            retrieval_mode=self.settings.retrieval_mode,
            top_k=self.settings.top_k,
        )
        if self.settings.evidence_search_cache_enabled:
            cached = self.evidence_search_cache.get(cache_key)
            if cached is not None:
                return cached
        sources = self._retrieve_sources(question) + self._retrieve_graph_sources(question)
        sources = self._dedupe_sources(sources)
        sources.sort(key=lambda source: source.score, reverse=True)
        compressed = self._compress_sources(sources)
        if self.settings.evidence_search_cache_enabled:
            self.evidence_search_cache.set(cache_key, compressed)
        return compressed

    def _retrieve_sources(self, question: str) -> list[SourceChunk]:
        matches = self.retriever.retrieve(
            question,
            top_k=self.settings.top_k,
            min_score=self.settings.min_confidence,
        )
        return [
            SourceChunk(
                chunk_id=match["chunk_id"],
                document_id=match["document_id"],
                document_name=match["document_name"],
                content=match["content"],
                score=match["score"],
                metadata=match.get("metadata", {}),
            )
            for match in matches
            if match["score"] >= self.settings.min_confidence
        ]

    def _retrieve_graph_sources(self, question: str) -> list[SourceChunk]:
        return [
            source
            for source in self.knowledge_graph.search(question, top_k=self.settings.top_k)
            if source.score >= self.settings.min_confidence
        ]

    def _dedupe_sources(self, sources: list[SourceChunk]) -> list[SourceChunk]:
        by_key: dict[str, SourceChunk] = {}
        for source in sources:
            key = source.chunk_id or f"{source.document_id}:{source.content[:80]}"
            existing = by_key.get(key)
            if existing is None or source.score > existing.score:
                by_key[key] = source
        return list(by_key.values())

    def _compress_sources(self, sources: list[SourceChunk]) -> list[SourceChunk]:
        per_document: dict[str, int] = {}
        compressed: list[SourceChunk] = []
        max_per_document = max(1, self.settings.source_max_chunks_per_document)
        for source in sources:
            count = per_document.get(source.document_id, 0)
            if count >= max_per_document:
                continue
            compressed.append(source)
            per_document[source.document_id] = count + 1
            if len(compressed) >= self.settings.top_k:
                break
        return compressed

    def _build_result(self, answer: str, sources: list[SourceChunk]) -> RagAnswer:
        confidence = sources[0].score if sources else 0.0
        return RagAnswer(
            answer=answer,
            sources=sources,
            confidence=confidence,
            is_answered=bool(sources),
            trace_id=f"qa_{uuid.uuid4().hex}",
        )

    def _cache_key(self, question: str) -> str:
        return answer_cache_key(
            question=question,
            knowledge_version=self.knowledge_version,
            retrieval_mode=self.settings.retrieval_mode,
            top_k=self.settings.top_k,
        )

    def _get_cached_answer(self, cache_key: str) -> RagAnswer | None:
        if not self.settings.answer_cache_enabled:
            return None
        return self.answer_cache.get(cache_key)

    def _set_cached_answer(self, cache_key: str, result: RagAnswer) -> None:
        if self.settings.answer_cache_enabled:
            self.answer_cache.set(cache_key, result)

    def _generate_answer(self, question: str, sources: list[SourceChunk], context_summary: str) -> str:
        try:
            return self.answer_generator.generate(question, sources, context_summary=context_summary)
        except TypeError:
            return self.answer_generator.generate(question, sources)

    def _generate_answer_stream(self, stream_method, question: str, sources: list[SourceChunk], context_summary: str):
        try:
            return stream_method(question, sources, context_summary=context_summary)
        except TypeError:
            return stream_method(question, sources)

    def _active_question(self, question: str, conversation_context: ConversationContext | None) -> str:
        if conversation_context is None:
            return question
        if not self.settings.question_expansion_enabled:
            return conversation_context.standalone_question
        candidates = (
            conversation_context.selected_questions
            or conversation_context.expanded_questions
            or [conversation_context.standalone_question]
        )
        ranked = rank_question_candidates(
            conversation_context.original_question,
            candidates,
            self.vector_store.list_records(),
            top_n=self.settings.question_expansion_top_n,
        )
        return ranked[0] if ranked else conversation_context.standalone_question

    def _context_summary(self, conversation_context: ConversationContext | None) -> str:
        if conversation_context is None:
            return ""
        parts = [conversation_context.context_summary]
        if conversation_context.selected_questions:
            parts.append("候选理解：" + "；".join(conversation_context.selected_questions))
        if conversation_context.assumptions:
            parts.append("默认假设：" + conversation_context.assumptions)
        return "；".join(part for part in parts if part)

    def _apply_assumptions(self, answer: str, conversation_context: ConversationContext | None) -> str:
        if not conversation_context or not conversation_context.assumptions or "### 温馨提示" not in answer:
            return answer
        if conversation_context.assumptions in answer:
            return answer
        return answer.replace("### 温馨提示\n", f"### 温馨提示\n{conversation_context.assumptions}\n", 1)

    def _meta_event(self, result: RagAnswer) -> dict[str, Any]:
        return {
            "type": "meta",
            "trace_id": result.trace_id,
            "confidence": result.confidence,
            "is_answered": result.is_answered,
            "needs_clarification": result.needs_clarification,
            "clarifying_question": result.clarifying_question,
            "sources": [
                {
                    "chunk_id": source.chunk_id,
                    "document_id": source.document_id,
                    "document_name": source.document_name,
                    "content_preview": source.content[:120],
                    "score": source.score,
                    "metadata": source.metadata,
                }
                for source in result.sources
            ],
        }

    def _split_cached_answer(self, answer: str) -> Iterator[str]:
        for start in range(0, len(answer), 24):
            yield answer[start : start + 24]

    def _write_qa_log(self, question: str, result: RagAnswer) -> None:
        self.settings.logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.settings.logs_dir / "qa.jsonl"
        record = {
            "trace_id": result.trace_id,
            "question": question,
            "answer": result.answer,
            "confidence": result.confidence,
            "is_answered": result.is_answered,
            "retrieval_mode": self.settings.retrieval_mode,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "sources": [
                {
                    "chunk_id": source.chunk_id,
                    "document_id": source.document_id,
                    "document_name": source.document_name,
                    "score": source.score,
                }
                for source in result.sources
            ],
        }
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _ensure_dirs(self) -> None:
        for directory in (
            self.settings.data_dir,
            self.settings.qdrant_db_dir,
            self.settings.logs_dir,
            self.settings.prompt_dir,
        ):
            Path(directory).mkdir(parents=True, exist_ok=True)

    def _document_id(self, document_name: str) -> str:
        stem = Path(document_name).stem or "document"
        return f"{stem}_{uuid.uuid4().hex[:8]}"

    def _document_id_from_md5(self, document_name: str, file_md5: str) -> str:
        stem = Path(document_name).stem or "document"
        return f"{stem}_{file_md5[:8]}"

    def _text_md5(self, text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def _is_uploaded_file(self, path: Path) -> bool:
        uploaded_dir = (self.settings.data_dir / "uploaded").resolve()
        target = path.resolve()
        return target.is_file() and target.parent == uploaded_dir
