from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from datetime import datetime, timezone
import uuid
from typing import Any

from lingjing_ai.agent.models import AgentAnswer, AgentEvidence, ToolResult, ToolTrace
from lingjing_ai.agent.planner import AgentPlanner
from lingjing_ai.config.settings import AppSettings
from lingjing_ai.models.rag import SourceChunk
from lingjing_ai.services.conversation import ConversationContext
from lingjing_ai.services.question_expansion import rank_question_candidates
from lingjing_ai.services.tool_intent import (
    classify_fast_tool_intent,
    route_endpoint_clarification,
    status_message_for_question,
)

# 可与 query_rewrite 解耦、彼此无依赖的检索类工具，适合并行。
_PARALLEL_TOOL_NAMES = frozenset(
    {
        "rag_search",
        "kg_search",
        "document_search",
        "web_search",
        "amap_weather",
        "amap_place",
        "amap_route",
    }
)


class AgentExecutor:
    def __init__(self, settings: AppSettings, tools: list[Any]) -> None:
        self.settings = settings
        self.planner = AgentPlanner(settings)
        self.tools = {tool.name: tool for tool in tools}
        self.pipeline = self._find_pipeline(tools)
        self.answer_generator = self._find_answer_generator(tools)

    def collect_evidence(
        self,
        question: str,
        conversation_context: ConversationContext | None = None,
        profile: str = "full",
    ) -> AgentEvidence:
        """Collect tool evidence without generating, so one final model serves text and voice modes."""
        active_question = self._active_question(question, conversation_context)
        if conversation_context and conversation_context.needs_clarification:
            return AgentEvidence(
                question=active_question,
                sources=[],
                confidence=0.0,
                is_answered=False,
                trace_id=f"evidence_{uuid.uuid4().hex}",
                tool_trace=[],
                needs_clarification=True,
                clarifying_question=conversation_context.clarifying_question,
            )
        route_clarification = route_endpoint_clarification(active_question)
        if route_clarification:
            return AgentEvidence(
                question=active_question,
                sources=[],
                confidence=0.0,
                is_answered=False,
                trace_id=f"evidence_{uuid.uuid4().hex}",
                tool_trace=[],
                needs_clarification=True,
                clarifying_question=route_clarification,
            )

        fast_evidence = self._collect_fast_tool_evidence(active_question)
        if fast_evidence is not None:
            return fast_evidence

        plan = self.planner.plan(active_question, profile=profile)
        traces, sources = self._execute_plan_steps(plan.steps, active_question)

        ranked = self._compress_sources(self._prioritize_sources(active_question, self._dedupe_sources(sources)))
        return AgentEvidence(
            question=active_question,
            sources=ranked,
            confidence=ranked[0].score if ranked else 0.0,
            is_answered=bool(ranked),
            trace_id=f"evidence_{uuid.uuid4().hex}",
            tool_trace=traces,
        )

    def _execute_plan_steps(
        self,
        steps: list[Any],
        active_question: str,
    ) -> tuple[list[ToolTrace], list[SourceChunk]]:
        """先串行跑 query_rewrite，再并行跑其余独立工具，缩短证据收集墙钟时间。"""
        queries = [active_question]
        traces: list[ToolTrace] = []
        sources: list[SourceChunk] = []
        pending: list[Any] = []

        for step in steps:
            tool = self.tools.get(step.tool_name)
            if tool is None:
                traces.append(ToolTrace(step.tool_name, step.tool_input, "skipped", "工具未注册"))
                continue
            if step.tool_name == "query_rewrite":
                result = self._run_tool(tool, step.tool_input, queries)
                traces.append(
                    ToolTrace(
                        tool_name=step.tool_name,
                        tool_input=step.tool_input,
                        status=result.status,
                        message=result.message,
                        source_count=len(result.sources),
                    )
                )
                if result.data.get("queries"):
                    queries = result.data["queries"][:3]
                sources.extend(result.sources)
                continue
            pending.append(step)

        if not pending:
            return traces, sources

        parallel_steps = [step for step in pending if step.tool_name in _PARALLEL_TOOL_NAMES]
        serial_steps = [step for step in pending if step.tool_name not in _PARALLEL_TOOL_NAMES]

        # 保持计划顺序写入 tool_trace：并行结果按原步骤下标回填。
        if len(parallel_steps) <= 1:
            ordered_results = [
                (step, self._run_tool(self.tools[step.tool_name], step.tool_input, queries))
                for step in parallel_steps
            ]
        else:
            ordered_results = [None] * len(parallel_steps)

            def _run_indexed(index: int, step: Any) -> tuple[int, Any, ToolResult]:
                tool = self.tools[step.tool_name]
                return index, step, self._run_tool(tool, step.tool_input, queries)

            workers = min(len(parallel_steps), 4)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [
                    pool.submit(_run_indexed, index, step)
                    for index, step in enumerate(parallel_steps)
                ]
                for future in as_completed(futures):
                    index, step, result = future.result()
                    ordered_results[index] = (step, result)

            ordered_results = [item for item in ordered_results if item is not None]

        for step, result in ordered_results:
            traces.append(
                ToolTrace(
                    tool_name=step.tool_name,
                    tool_input=step.tool_input,
                    status=result.status,
                    message=result.message,
                    source_count=len(result.sources),
                )
            )
            sources.extend(result.sources)

        for step in serial_steps:
            tool = self.tools[step.tool_name]
            result = self._run_tool(tool, step.tool_input, queries)
            traces.append(
                ToolTrace(
                    tool_name=step.tool_name,
                    tool_input=step.tool_input,
                    status=result.status,
                    message=result.message,
                    source_count=len(result.sources),
                )
            )
            sources.extend(result.sources)

        return traces, sources

    def _collect_fast_tool_evidence(self, question: str) -> AgentEvidence | None:
        if not self.settings.agent_fast_tool_path_enabled:
            return None
        intent = classify_fast_tool_intent(question)
        if intent is None:
            return None
        tool = self.tools.get(intent.tool_name)
        if tool is None:
            return None
        result = tool.run(question)
        sources = self._compress_sources(self._prioritize_sources(question, self._dedupe_sources(result.sources)))
        trace = ToolTrace(
            tool_name=intent.tool_name,
            tool_input=question,
            status=result.status,
            message=result.message,
            source_count=len(result.sources),
        )
        return AgentEvidence(
            question=question,
            sources=sources,
            confidence=sources[0].score if sources else 0.0,
            is_answered=bool(sources),
            trace_id=f"evidence_{uuid.uuid4().hex}",
            tool_trace=[trace],
        )

    def run(self, question: str, conversation_context: ConversationContext | None = None) -> AgentAnswer:
        active_question = self._active_question(question, conversation_context)
        if conversation_context and conversation_context.needs_clarification:
            result = AgentAnswer(
                answer=conversation_context.clarifying_question,
                sources=[],
                confidence=0.0,
                is_answered=False,
                trace_id=f"agent_{uuid.uuid4().hex}",
                tool_trace=[],
                needs_clarification=True,
                clarifying_question=conversation_context.clarifying_question,
            )
            self._write_agent_log(active_question, result)
            return result
        route_clarification = route_endpoint_clarification(active_question)
        if route_clarification:
            result = AgentAnswer(
                answer=route_clarification,
                sources=[],
                confidence=0.0,
                is_answered=False,
                trace_id=f"agent_{uuid.uuid4().hex}",
                tool_trace=[],
                needs_clarification=True,
                clarifying_question=route_clarification,
            )
            self._write_agent_log(active_question, result)
            return result
        fast_result = self._run_fast_tool_answer(active_question, conversation_context)
        if fast_result is not None:
            self._write_agent_log(active_question, fast_result)
            return fast_result

        plan = self.planner.plan(active_question, profile="full")
        traces, sources = self._execute_plan_steps(plan.steps, active_question)

        ranked_sources = self._compress_sources(self._prioritize_sources(active_question, self._dedupe_sources(sources)))
        answer = self._apply_assumptions(self._generate_answer(active_question, ranked_sources, conversation_context), conversation_context)
        result = AgentAnswer(
            answer=answer,
            sources=ranked_sources,
            confidence=ranked_sources[0].score if ranked_sources else 0.0,
            is_answered=bool(ranked_sources),
            trace_id=f"agent_{uuid.uuid4().hex}",
            tool_trace=traces,
        )
        self._write_agent_log(active_question, result)
        return result

    def run_stream(self, question: str, conversation_context: ConversationContext | None = None) -> Iterator[dict[str, Any]]:
        active_question = self._active_question(question, conversation_context)
        if conversation_context and conversation_context.needs_clarification:
            yield {"type": "status", "message": "正在分析问题"}
            result = self.run(question, conversation_context=conversation_context)
            yield from self._stream_result(result)
            return

        fast_result = self._run_fast_tool_answer(active_question, conversation_context)
        if fast_result is not None:
            yield {"type": "status", "message": status_message_for_question(active_question)}
            self._write_agent_log(active_question, fast_result)
            yield from self._stream_result(fast_result)
            return

        yield {"type": "status", "message": "正在分析问题"}
        yield {"type": "status", "message": status_message_for_question(active_question)}
        result = self.run(question, conversation_context=conversation_context)
        yield from self._stream_result(result)

    def _stream_result(self, result: AgentAnswer) -> Iterator[dict[str, Any]]:
        yield {
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
            "tool_trace": [trace.__dict__ for trace in result.tool_trace],
        }
        yield {"type": "status", "message": "正在整理答案"}
        for token in self._split_answer(result.answer):
            yield {"type": "token", "content": token}
        yield {"type": "done", "trace_id": result.trace_id}

    def _run_fast_tool_answer(
        self,
        active_question: str,
        conversation_context: ConversationContext | None,
    ) -> AgentAnswer | None:
        if not self.settings.agent_fast_tool_path_enabled:
            return None
        intent = classify_fast_tool_intent(active_question)
        if intent is None:
            return None
        tool = self.tools.get(intent.tool_name)
        if tool is None:
            return None

        tool_result = tool.run(active_question)
        traces = [
            ToolTrace(
                tool_name=intent.tool_name,
                tool_input=active_question,
                status=tool_result.status,
                message=tool_result.message,
                source_count=len(tool_result.sources),
            )
        ]
        sources = self._compress_sources(self._prioritize_sources(active_question, self._dedupe_sources(tool_result.sources)))
        if self.settings.agent_simple_tool_direct_answer and intent.direct_answer:
            answer = self._format_direct_tool_answer(tool_result)
        else:
            answer = self._apply_assumptions(
                self._generate_answer(active_question, sources, conversation_context),
                conversation_context,
            )
        return AgentAnswer(
            answer=answer,
            sources=sources,
            confidence=sources[0].score if sources else 0.0,
            is_answered=bool(sources),
            trace_id=f"agent_{uuid.uuid4().hex}",
            tool_trace=traces,
        )

    def _run_tool(self, tool: Any, tool_input: str, queries: list[str]) -> ToolResult:
        if tool.name in {"rag_search", "kg_search", "document_search"}:
            sources: list[SourceChunk] = []
            status = "empty"
            message = "未命中相关内容"
            for query in queries:
                result = tool.run(query)
                sources.extend(result.sources)
                if result.status == "ok":
                    status = "ok"
                    message = result.message
            return ToolResult(status=status, message=message, sources=sources)
        return tool.run(tool_input)

    def _dedupe_sources(self, sources: list[SourceChunk]) -> list[SourceChunk]:
        by_key: dict[str, SourceChunk] = {}
        for source in sources:
            key = source.chunk_id or f"{source.document_id}:{source.content[:60]}"
            existing = by_key.get(key)
            if existing is None or source.score > existing.score:
                by_key[key] = source
        return sorted(by_key.values(), key=lambda source: source.score, reverse=True)

    def _prioritize_sources(self, question: str, sources: list[SourceChunk]) -> list[SourceChunk]:
        priority_source_type = _preferred_tool_source_type(question)
        if priority_source_type is None:
            return sources
        return sorted(
            sources,
            key=lambda source: (
                source.metadata.get("source_type") == priority_source_type,
                source.score,
            ),
            reverse=True,
        )

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

    def _find_answer_generator(self, tools: list[Any]):
        pipeline = self._find_pipeline(tools)
        return pipeline.answer_generator

    def _find_pipeline(self, tools: list[Any]):
        for tool in tools:
            pipeline = getattr(tool, "pipeline", None)
            if pipeline is not None:
                return pipeline
        raise ValueError("AgentExecutor requires at least one pipeline-backed tool.")

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
            self.pipeline.vector_store.list_records(),
            top_n=self.settings.question_expansion_top_n,
        )
        return ranked[0] if ranked else conversation_context.standalone_question

    def _generate_answer(
        self,
        question: str,
        sources: list[SourceChunk],
        conversation_context: ConversationContext | None,
    ) -> str:
        context_summary = conversation_context.context_summary if conversation_context else ""
        try:
            return self.answer_generator.generate(question, sources, context_summary=context_summary)
        except TypeError:
            return self.answer_generator.generate(question, sources)

    def _split_answer(self, answer: str) -> Iterator[str]:
        for start in range(0, len(answer), 24):
            yield answer[start : start + 24]

    def _format_direct_tool_answer(self, tool_result: ToolResult) -> str:
        if not tool_result.sources:
            return (
                "### 简要回答\n"
                f"{tool_result.message or '当前工具没有返回可用结果。'}\n\n"
                "### 详细说明\n"
                "- 暂时没有查到可直接使用的地图或天气数据。\n\n"
                "### 温馨提示\n"
                "请补充更明确的地点，或稍后再试。\n\n"
                "依据：高德地图工具"
            )

        source = tool_result.sources[0]
        source_type = source.metadata.get("source_type")
        if source_type == "amap_weather":
            return (
                "### 简要回答\n"
                f"{source.content}\n\n"
                "### 详细说明\n"
                f"- 查询城市：{source.metadata.get('city', '未知')}\n"
                f"- 天气：{source.metadata.get('weather', '未知')}\n"
                f"- 气温：{source.metadata.get('temperature', '未知')}℃\n"
                f"- 风力：{source.metadata.get('winddirection', '未知')}风{source.metadata.get('windpower', '未知')}级\n"
                f"- 湿度：{source.metadata.get('humidity', '未知')}%\n\n"
                "### 温馨提示\n"
                "天气会随时间变化，出行前建议再次确认，并结合防晒、防雨和舒适鞋履安排。\n\n"
                "依据：高德天气"
            )
        if source_type == "amap_route":
            metadata = source.metadata
            steps = metadata.get("steps") or []
            step_lines = "\n".join(
                f"- {step.get('instruction', '')}" for step in steps[:5] if step.get("instruction")
            ) or "- 高德未返回详细步骤。"
            return (
                "### 简要回答\n"
                f"{source.content}\n\n"
                "### 详细说明\n"
                f"- 起点：{metadata.get('origin', '未知')}\n"
                f"- 终点：{metadata.get('destination', '未知')}\n"
                f"- 出行方式：{'步行' if metadata.get('mode') == 'walking' else '驾车'}\n"
                f"- 总距离：{metadata.get('distance_text', '未知距离')}\n"
                f"- 预计时间：{metadata.get('duration_text', '未知时间')}\n"
                f"{step_lines}\n\n"
                "### 温馨提示\n"
                "实际耗时会受交通、排队和停车情况影响，建议出发前查看高德实时路况。\n\n"
                "依据：高德路线规划"
            )
        if source_type == "amap_place":
            return (
                "### 简要回答\n"
                f"{source.content}\n\n"
                "### 详细说明\n"
                "- 已优先使用高德地点数据返回位置、地址和坐标信息。\n\n"
                "### 温馨提示\n"
                "地点营业状态和入口位置可能变化，出行前建议在地图中再次确认。\n\n"
                "依据：高德地图地点查询"
            )
        return (
            "### 简要回答\n"
            f"{source.content}\n\n"
            "### 详细说明\n"
            "- 已根据可用工具结果直接整理回答。\n\n"
            "### 温馨提示\n"
            "如需更精确的信息，可以补充时间、地点或出行方式。\n\n"
            f"依据：{source.document_name}"
        )

    def _apply_assumptions(self, answer: str, conversation_context: ConversationContext | None) -> str:
        if not conversation_context or not conversation_context.assumptions or "### 温馨提示" not in answer:
            return answer
        if conversation_context.assumptions in answer:
            return answer
        return answer.replace("### 温馨提示\n", f"### 温馨提示\n{conversation_context.assumptions}\n", 1)

    def _write_agent_log(self, question: str, result: AgentAnswer) -> None:
        self.settings.logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.settings.logs_dir / "agent.jsonl"
        record = {
            "trace_id": result.trace_id,
            "question": question,
            "answer": result.answer,
            "confidence": result.confidence,
            "is_answered": result.is_answered,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tool_trace": [trace.__dict__ for trace in result.tool_trace],
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


def _preferred_tool_source_type(question: str) -> str | None:
    intent = classify_fast_tool_intent(question)
    return intent.source_type if intent is not None else None
