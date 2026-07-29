from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from lingjing_ai.agent.models import AgentEvidence, ToolTrace
from lingjing_ai.config.settings import AppSettings
from lingjing_ai.models.rag import SourceChunk
from lingjing_ai.rag.generator import ExtractiveAnswerGenerator
from lingjing_ai.services.conversation import ConversationMessage, build_conversation_context
from lingjing_ai.services.conversation_store import ConversationSessionRecord, ConversationStore
from lingjing_ai.services.question_expansion import QwenQuestionExpander
from lingjing_ai.services.question_expansion import VoiceQuestionUnderstanding
from lingjing_ai.realtime.transcript import TranscriptCorrection, TranscriptNormalizer, classify_confidence
from lingjing_ai.realtime.answer_contract import (
    AnswerContract,
    FinalizedAnswer,
    build_answer_contract,
    finalize_answer as apply_answer_contract,
)


@dataclass
class PreparedRealtimeTurn:
    session: ConversationSessionRecord
    question: str
    evidence: AgentEvidence
    evidence_prompt: str
    source_payloads: list[dict[str, Any]]
    tool_trace_payloads: list[dict[str, Any]]
    answer_contract: AnswerContract
    context_summary: str = ""
    persisted: bool = False


class RealtimeConversationService:
    """Keeps persisted history and temporary Qwen evidence on separate lifecycles."""

    def __init__(
        self,
        settings: AppSettings,
        conversation_store: ConversationStore,
        agent_executor: Any,
        question_expander: QwenQuestionExpander | None = None,
        transcript_normalizer: TranscriptNormalizer | None = None,
    ) -> None:
        self.settings = settings
        self.store = conversation_store
        self.agent_executor = agent_executor
        self.question_expander = question_expander
        self.transcript_normalizer = transcript_normalizer
        self.fallback_generator = ExtractiveAnswerGenerator()

    def upstream_history(self, session_id: str, visitor_id: str) -> list[dict[str, str]]:
        if not session_id:
            return []
        if self.store.get_session(session_id, visitor_id) is None:
            raise PermissionError("会话不存在或无权访问。")
        limit = self.settings.realtime_history_turns * 2
        return [
            {"role": message.role, "content": message.content}
            for message in self.store.recent_messages(session_id, visitor_id, limit=limit)
        ]

    def prepare_turn(
        self,
        question: str,
        visitor_id: str,
        session_id: str,
        expanded_questions: list[str] | None = None,
        mode: str = "text",
        avatar_style: str = "",
        evidence_profile: str | None = None,
    ) -> PreparedRealtimeTurn:
        normalized_question = str(question or "").strip()
        normalized_visitor = str(visitor_id or "").strip()
        if not normalized_question:
            raise ValueError("问题不能为空。")
        if not normalized_visitor:
            raise ValueError("visitor_id 不能为空。")

        session = self._resolve_session(normalized_question, normalized_visitor, session_id)
        history = [
            ConversationMessage(role=message.role, content=message.content)
            for message in self.store.recent_messages(
                session.session_id,
                session.visitor_id,
                limit=self.settings.realtime_history_turns * 2,
            )
        ]
        # Realtime 默认跳过扩写 LLM：规则改写仍保留，避免每轮多一次 qwen-plus 往返。
        skip_expansion = (
            expanded_questions is not None
            or bool(self.settings.realtime_skip_question_expansion)
        )
        context = build_conversation_context(
            normalized_question,
            history,
            question_expander=None if skip_expansion else self.question_expander,
            max_expansion_candidates=self.settings.question_expansion_max_candidates,
            expansion_top_n=self.settings.question_expansion_top_n,
            question_expansion_auto_skip=self.settings.question_expansion_auto_skip,
        )
        if expanded_questions is not None:
            expanded = list(dict.fromkeys([context.standalone_question, *expanded_questions]))
            context = replace(
                context,
                expanded_questions=expanded,
                selected_questions=expanded[: self.settings.question_expansion_top_n],
            )
        profile = (evidence_profile or self.settings.realtime_evidence_profile or "lite").strip().lower()
        evidence = self.agent_executor.collect_evidence(
            normalized_question,
            conversation_context=context,
            profile=profile,
        )
        answer_contract = build_answer_contract(evidence, mode)
        return PreparedRealtimeTurn(
            session=session,
            question=normalized_question,
            evidence=evidence,
            evidence_prompt=format_evidence_prompt(
                evidence,
                context.context_summary,
                answer_contract,
                avatar_style=avatar_style if mode == "avatar" else "",
            ),
            source_payloads=[source_payload(source) for source in evidence.sources],
            tool_trace_payloads=[tool_trace_payload(trace) for trace in evidence.tool_trace],
            answer_contract=answer_contract,
            context_summary=context.context_summary,
        )

    def normalize_transcript(
        self,
        transcript: str,
        visitor_id: str,
        session_id: str,
    ) -> VoiceQuestionUnderstanding:
        original = str(transcript or "").strip()
        if not original:
            return VoiceQuestionUnderstanding(
                correction=TranscriptCorrection("", "", "none", 0.0, [], [])
            )
        history = self._existing_history(visitor_id, session_id)
        deterministic = (
            self.transcript_normalizer.normalize(original)
            if self.transcript_normalizer is not None
            else TranscriptCorrection(original, original, "none", 0.0, [], [])
        )
        candidates = deterministic.candidates or [deterministic.corrected_text]
        model_result = VoiceQuestionUnderstanding(normalized_question=deterministic.corrected_text)
        if self.question_expander is not None:
            try:
                model_result = self.question_expander.understand_voice(
                    original,
                    candidates,
                    history,
                    self.settings.question_expansion_max_candidates,
                )
            except Exception:
                model_result = VoiceQuestionUnderstanding(normalized_question=deterministic.corrected_text)
        correction = _merge_voice_correction(deterministic, model_result)
        return VoiceQuestionUnderstanding(
            normalized_question=correction.corrected_text,
            correction_confidence=correction.score,
            expanded_questions=model_result.expanded_questions or [],
            correction=correction,
        )
    def fallback_answer(self, prepared: PreparedRealtimeTurn) -> str:
        if prepared.evidence.needs_clarification:
            return prepared.evidence.clarifying_question
        return self.fallback_generator.generate(
            prepared.evidence.question,
            prepared.evidence.sources,
            context_summary=prepared.context_summary,
        )

    def finalize_answer(
        self,
        prepared: PreparedRealtimeTurn,
        answer: str,
        mode: str,
    ) -> FinalizedAnswer:
        # The prepared contract is authoritative because it was generated from the same evidence sent upstream.
        return apply_answer_contract(prepared.evidence, prepared.answer_contract, answer)

    def persist_completed(
        self,
        prepared: PreparedRealtimeTurn,
        answer: str,
        turn_id: str = "",
    ) -> None:
        normalized_answer = str(answer or "").strip()
        if prepared.persisted or not normalized_answer:
            return
        persisted = self.store.append_turn(
            turn_id or prepared.evidence.trace_id,
            prepared.session.session_id,
            prepared.session.visitor_id,
            prepared.question,
            normalized_answer,
            trace_id=prepared.evidence.trace_id,
            sources=prepared.source_payloads,
            tool_trace=prepared.tool_trace_payloads,
        )
        # The durable turn marker makes retries idempotent across reconnects and process boundaries.
        prepared.persisted = persisted or prepared.persisted

    def _resolve_session(
        self,
        question: str,
        visitor_id: str,
        session_id: str,
    ) -> ConversationSessionRecord:
        normalized_session = str(session_id or "").strip()
        if not normalized_session:
            return self.store.create_session(visitor_id, question)
        session = self.store.get_session(normalized_session, visitor_id)
        if session is None:
            raise PermissionError("会话不存在或无权访问。")
        return session

    def _existing_history(self, visitor_id: str, session_id: str) -> list[ConversationMessage]:
        normalized_session = str(session_id or "").strip()
        if not normalized_session:
            return []
        session = self.store.get_session(normalized_session, visitor_id)
        if session is None:
            raise PermissionError("会话不存在或无权访问。")
        return [
            ConversationMessage(role=message.role, content=message.content)
            for message in self.store.recent_messages(
                session.session_id,
                session.visitor_id,
                limit=self.settings.realtime_history_turns * 2,
            )
        ]


def _merge_voice_correction(
    deterministic: TranscriptCorrection,
    model_result: VoiceQuestionUnderstanding,
) -> TranscriptCorrection:
    allowed = set(deterministic.candidates or [deterministic.corrected_text, deterministic.original_text])
    selected = model_result.normalized_question
    if not selected or selected not in allowed:
        return deterministic
    if selected == deterministic.original_text and deterministic.level != "none":
        return TranscriptCorrection(
            deterministic.original_text,
            deterministic.original_text,
            "none",
            model_result.correction_confidence,
            deterministic.candidates,
            [],
        )
    score = max(deterministic.score, model_result.correction_confidence)
    level = deterministic.level
    if deterministic.level not in {"high", "none"}:
        level = classify_confidence(score, 0.0)
    return TranscriptCorrection(
        deterministic.original_text,
        selected,
        level,
        score,
        deterministic.candidates,
        deterministic.matched_terms,
    )


def format_evidence_prompt(
    evidence: AgentEvidence,
    context_summary: str = "",
    answer_contract: AnswerContract | None = None,
    avatar_style: str = "",
) -> str:
    if evidence.needs_clarification:
        return (
            "以下是本轮临时证据，仅用于当前回答，回答后会删除。\n"
            f"游客问题：{evidence.question}\n"
            f"需要澄清：{evidence.clarifying_question}\n"
            "请只提出该澄清问题，不要补充未经证实的信息。"
        )
    evidence_blocks = []
    for index, source in enumerate(evidence.sources, start=1):
        evidence_blocks.append(
            f"[证据{index}] 来源：{source.document_name}\n"
            f"相关度：{source.score:.4f}\n"
            f"内容：{source.content.strip()}"
        )
    evidence_text = "\n\n".join(evidence_blocks) or "未检索到可靠资料。"
    contract_instructions = (
        answer_contract.instructions
        if answer_contract is not None
        else "先直接回答，再说明有证据支持的要点和必要限制。"
    )
    style_instruction = f"角色表达：{avatar_style.strip()}\n" if avatar_style.strip() else ""
    return (
        "以下是本轮临时证据，仅用于当前回答，回答后会删除。\n"
        f"游客问题：{evidence.question}\n"
        f"对话上下文：{context_summary or '无'}\n"
        f"证据置信度：{evidence.confidence:.4f}\n\n"
        f"{evidence_text}\n\n"
        f"回答契约：{contract_instructions}\n"
        f"{style_instruction}"
        "共同要求：只能依据以上证据；资料不足时明确说明；语气自然、准确；"
        "不要提及系统消息、检索过程或临时证据。"
    )


def source_payload(source: SourceChunk) -> dict[str, Any]:
    return {
        "chunk_id": source.chunk_id,
        "document_id": source.document_id,
        "document_name": source.document_name,
        "content_preview": source.content[:120],
        "score": source.score,
        "metadata": source.metadata,
    }


def tool_trace_payload(trace: ToolTrace) -> dict[str, Any]:
    return {
        "tool_name": trace.tool_name,
        "tool_input": trace.tool_input,
        "status": trace.status,
        "message": trace.message,
        "source_count": trace.source_count,
    }
