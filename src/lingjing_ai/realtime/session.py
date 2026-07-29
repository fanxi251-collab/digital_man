from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
import logging
from typing import Any

from fastapi import WebSocketDisconnect

from lingjing_ai.config.settings import AppSettings
from lingjing_ai.realtime.avatar_profiles import (
    DEFAULT_AVATAR_ID,
    resolve_avatar_profile,
)
from lingjing_ai.realtime.connection_lifecycle import (
    RealtimeClientFactory,
    RealtimeConnectionLifecycle,
)
from lingjing_ai.realtime.conversation import PreparedRealtimeTurn, RealtimeConversationService
from lingjing_ai.realtime.qwen_audio import QwenAudioRealtimeClient
from lingjing_ai.services.question_expansion import VoiceQuestionUnderstanding


LOGGER = logging.getLogger(__name__)


@dataclass
class PendingTurn:
    turn_id: str
    mode: str
    prepared: PreparedRealtimeTurn
    avatar_id: str = DEFAULT_AVATAR_ID
    answer_parts: list[str] = field(default_factory=list)
    evidence_item_id: str = ""
    user_item_id: str = ""
    output_item_id: str = ""
    response_id: str = ""
    response_created: asyncio.Event = field(default_factory=asyncio.Event)
    audio_started: bool = False


@dataclass
class PendingTranscript:
    turn_id: str
    upstream_item_id: str
    understanding: VoiceQuestionUnderstanding


class VisitorRealtimeSession(RealtimeConnectionLifecycle):
    """Bridges browser events to one Qwen connection while committing only full turns."""

    def __init__(
        self,
        browser: Any,
        visitor_id: str,
        session_id: str,
        settings: AppSettings,
        conversation_service: RealtimeConversationService,
        qwen_client: QwenAudioRealtimeClient,
        qwen_client_factory: RealtimeClientFactory | None = None,
        avatar_id: str = DEFAULT_AVATAR_ID,
    ) -> None:
        self.browser = browser
        self.visitor_id = str(visitor_id or "").strip()
        self.session_id = str(session_id or "").strip()
        self.settings = settings
        self.service = conversation_service
        self.qwen = qwen_client
        self._qwen_client_factory = qwen_client_factory
        self.mode = "text"
        self.avatar_id = avatar_id
        self.pending: PendingTurn | None = None
        self.pending_transcript: PendingTranscript | None = None
        self.audio_turn_id = ""
        self.audio_transcript_parts: list[str] = []
        self.upstream_available = False
        # asyncio.Lock 保证 JSON/PCM 出站 FIFO，audio.started 严格先于首块 PCM。
        self._send_lock = asyncio.Lock()
        self._turn_transition_lock = asyncio.Lock()
        self._finalization_done = asyncio.Event()
        self._finalization_done.set()
        self._reconnect_failures = 0
        self._stale_response_ids: set[str] = set()
        self._upstream_task: asyncio.Task[Any] | None = None
        self._run_started = False
        self._connection_generation = 0
        self._avatar_switch_lock = asyncio.Lock()
        self._avatar_switching = False

    async def open(self) -> None:
        history = await asyncio.to_thread(
            self.service.upstream_history,
            self.session_id,
            self.visitor_id,
        )
        try:
            await self.qwen.open(history, self._session_config(self.avatar_id))
            self.upstream_available = True
            self._connection_generation += 1
        except Exception as exc:
            self.upstream_available = False
            await self._send_error("UPSTREAM_CONNECT_FAILED", str(exc), recoverable=True)
        await self._send_json(
            {
                "type": "session.ready",
                "mode": self.mode,
                "avatar_id": self.avatar_id,
                "voice": self._profile(self.avatar_id).voice,
                "upstream_available": self.upstream_available,
            }
        )
        if self.session_id:
            await self._send_json({"type": "session.bound", "session_id": self.session_id})

    async def close(self) -> None:
        await self.qwen.close()

    async def run(self) -> None:
        self._run_started = True
        if self.upstream_available:
            self._start_upstream_task()
        try:
            await self._browser_loop()
        finally:
            self._run_started = False
            await self._stop_upstream_task()
            await self.close()

    async def handle_client_event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type", ""))
        if event_type == "mode.set":
            mode = str(event.get("mode", ""))
            if mode not in {"text", "avatar"}:
                await self._send_error("INVALID_MODE", "mode 仅支持 text 或 avatar。")
                return
            if mode != self.mode and (self.pending or self.pending_transcript or self.audio_turn_id):
                await self._cancel_current(str(event.get("turn_id", "")))
            self.mode = mode
            return
        if event_type == "avatar.set":
            requested_avatar_id = str(event.get("avatar_id", "")).strip()
            if resolve_avatar_profile(self.settings, requested_avatar_id) is None:
                await self._send_error("INVALID_AVATAR", "不支持的数字人角色。")
                return
            await self._switch_avatar(requested_avatar_id)
            return
        if event_type == "text.submit":
            if await self._reject_during_avatar_switch():
                return
            await self._start_question(
                str(event.get("text", "")),
                str(event.get("turn_id", "")),
                inject_user=True,
            )
            return
        if event_type == "audio.start":
            if await self._reject_during_avatar_switch():
                return
            await self._start_audio(str(event.get("turn_id", "")))
            return
        if event_type == "audio.commit":
            await self._commit_audio(str(event.get("turn_id", "")))
            return
        if event_type == "transcript.confirm":
            await self._confirm_transcript(
                str(event.get("turn_id", "")),
                str(event.get("text", "")),
            )
            return
        if event_type == "response.cancel":
            await self._cancel_current(str(event.get("turn_id", "")))
            return
        await self._send_error("UNKNOWN_EVENT", f"不支持的客户端事件：{event_type}")

    async def handle_audio_frame(self, pcm: bytes) -> None:
        if await self._reject_during_avatar_switch():
            return
        if self.mode != "avatar" or not self.audio_turn_id:
            await self._send_error("AUDIO_NOT_STARTED", "请先在数字人模式开始录音。")
            return
        if not self.upstream_available:
            await self._send_error("AUDIO_UNAVAILABLE", "语音服务暂不可用，请使用文字输入。")
            return
        await self.qwen.append_audio(pcm)

    async def handle_upstream_event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type", ""))
        if event_type == "error":
            error = event.get("error") or {}
            if str(error.get("param") or "") == "response.create" and self.pending:
                await self._fallback_current("实时回答失败，已使用本地证据文本。")
            else:
                await self._send_error(
                    str(error.get("code") or "UPSTREAM_EVENT_ERROR"),
                    str(error.get("message") or "实时模型返回了控制事件错误。"),
                    recoverable=True,
                )
            return
        if event_type.endswith("input_audio_transcription.delta"):
            delta = _event_text(event)
            if delta:
                self.audio_transcript_parts.append(delta)
                await self._send_json({"type": "user.transcript.delta", "delta": delta})
            return
        if event_type.endswith("input_audio_transcription.completed"):
            transcript = str(event.get("transcript") or event.get("text") or "").strip()
            if not transcript:
                transcript = "".join(self.audio_transcript_parts).strip()
            self.audio_transcript_parts.clear()
            turn_id = self.audio_turn_id
            self.audio_turn_id = ""
            if not transcript:
                await self._send_json(
                    {"type": "turn.cancelled", "turn_id": turn_id, "reason": "empty_transcript"}
                )
                return
            await self._handle_completed_transcript(
                transcript,
                turn_id,
                str(event.get("item_id") or ""),
            )
            return
        if event_type == "response.created":
            response_id = _response_id(event)
            if self.pending is not None:
                self.pending.response_id = response_id
                self.pending.response_created.set()
                actual_voice = str((event.get("response") or {}).get("voice") or "").strip()
                expected_voice = self._profile(self.pending.avatar_id).voice
                if self.pending.mode == "avatar":
                    LOGGER.info(
                        "realtime_response_voice turn_id=%s avatar_id=%s expected=%s actual=%s",
                        self.pending.turn_id,
                        self.pending.avatar_id,
                        expected_voice,
                        actual_voice or "unknown",
                    )
                if (
                    self.pending.mode == "avatar"
                    and actual_voice
                    and actual_voice != expected_voice
                ):
                    await self.qwen.cancel_response()
                    await self._send_error(
                        "AVATAR_VOICE_MISMATCH",
                        "数字人音色初始化不一致，本轮已停止语音并改用文字回答。",
                        recoverable=True,
                    )
                    await self._fallback_current(
                        "数字人音色初始化不一致，本轮已使用本地证据文本。"
                    )
            elif response_id:
                self._stale_response_ids.add(response_id)
            return
        if self.pending is None:
            return
        response_id = _response_id(event)
        if response_id and response_id in self._stale_response_ids:
            if event_type == "response.output_item.added":
                stale_item_id = str((event.get("item") or {}).get("id") or "")
                if stale_item_id:
                    try:
                        await self.qwen.delete_item(stale_item_id)
                    except Exception:
                        pass
            return
        if self.pending.response_id and response_id and response_id != self.pending.response_id:
            return
        if event_type == "response.output_item.added":
            self.pending.output_item_id = str((event.get("item") or {}).get("id") or "")
            return
        if _is_answer_delta(event_type, self.pending.mode):
            delta = _event_text(event)
            if delta:
                self.pending.answer_parts.append(delta)
                await self._send_json(
                    {
                        "type": "assistant.text.delta",
                        "turn_id": self.pending.turn_id,
                        "delta": delta,
                    }
                )
            return
        if event_type == "response.audio.delta" and self.pending.mode == "avatar":
            encoded = str(event.get("delta") or "")
            if not encoded:
                return
            if not self.pending.audio_started:
                self.pending.audio_started = True
                await self._send_json(
                    {"type": "assistant.audio.started", "turn_id": self.pending.turn_id}
                )
            await self._send_bytes(base64.b64decode(encoded))
            return
        if event_type == "response.audio.done" and self.pending.mode == "avatar":
            await self._send_json(
                {"type": "assistant.audio.done", "turn_id": self.pending.turn_id}
            )
            return
        if event_type == "response.done":
            status = str((event.get("response") or {}).get("status", "completed"))
            if status in {"cancelled", "canceled"}:
                await self._finish_cancelled("upstream_cancelled", _response_id(event))
            elif status == "completed":
                await self._finish_completed(event)
            else:
                await self._fallback_current("实时回答失败，已使用本地证据文本。")
            return

    async def _start_question(
        self,
        question: str,
        turn_id: str,
        inject_user: bool,
        user_item_id: str = "",
        expanded_questions: list[str] | None = None,
    ) -> None:
        async with self._turn_transition_lock:
            await self._finalization_done.wait()
            pending = await self._reserve_question(
                question,
                turn_id,
                user_item_id,
                expanded_questions,
            )
        if pending is None:
            return
        route_error = getattr(getattr(pending.prepared, "answer_contract", None), "route_error", "")
        if route_error:
            # A deterministic tool error must bypass Qwen so no speculative route can be streamed or spoken.
            await self._fallback_current(route_error)
            return
        if not self.upstream_available:
            await self._fallback_current("语音模型暂不可用，已使用本地证据文本。")
            return
        try:
            if inject_user:
                pending.user_item_id = await self.qwen.inject_message(
                    "user", pending.prepared.question
                )
            pending.evidence_item_id = await self.qwen.inject_evidence(
                pending.prepared.evidence_prompt
            )
            await self.qwen.create_response(pending.mode)
        except Exception:
            # A failed upstream send still has complete Agent evidence, so preserve the turn via text fallback.
            await self._fallback_current("实时回答请求失败，已使用本地证据文本。")

    async def _reserve_question(
        self,
        question: str,
        turn_id: str,
        user_item_id: str,
        expanded_questions: list[str] | None,
    ) -> PendingTurn | None:
        normalized_question = question.strip()
        normalized_turn_id = turn_id.strip()
        if not normalized_question or not normalized_turn_id:
            await self._send_error("INVALID_TURN", "turn_id 和问题文本不能为空。")
            return
        if self.pending is not None:
            await self._cancel_current(self.pending.turn_id)
        if resolve_avatar_profile(self.settings, self.avatar_id) is None:
            await self._send_error("INVALID_AVATAR", "当前数字人角色不可用。")
            return
        try:
            prepared = await asyncio.to_thread(
                self.service.prepare_turn,
                normalized_question,
                self.visitor_id,
                self.session_id,
                expanded_questions=expanded_questions,
                mode=self.mode,
                # Persona now lives in the first session.update so evidence remains factual and temporary.
                avatar_style="",
            )
        except PermissionError as exc:
            await self._send_error("SESSION_FORBIDDEN", str(exc))
            return
        except Exception as exc:
            await self._send_error("EVIDENCE_FAILED", str(exc))
            return

        self.session_id = prepared.session.session_id
        # Snapshot the role so a response cannot change voice or persona midway through a turn.
        self.pending = PendingTurn(
            normalized_turn_id,
            self.mode,
            prepared,
            avatar_id=self.avatar_id,
        )
        self.pending.user_item_id = user_item_id
        await self._send_json(
            {
                "type": "session.bound",
                "session_id": self.session_id,
                "session_title": prepared.session.title,
            }
        )
        await self._send_json({"type": "turn.accepted", "turn_id": normalized_turn_id})
        await self._send_json(
            {
                "type": "agent.meta",
                "turn_id": normalized_turn_id,
                "trace_id": prepared.evidence.trace_id,
                "confidence": prepared.evidence.confidence,
                "sources": prepared.source_payloads,
                "tool_trace": prepared.tool_trace_payloads,
            }
        )
        return self.pending

    async def _start_audio(self, turn_id: str) -> None:
        if self.mode != "avatar":
            await self._send_error("INVALID_MODE", "录音仅在数字人模式可用。")
            return
        if not turn_id.strip():
            await self._send_error("INVALID_TURN", "turn_id 不能为空。")
            return
        if self.pending or self.pending_transcript or self.audio_turn_id:
            current_turn_id = (
                self.pending.turn_id if self.pending
                else self.pending_transcript.turn_id if self.pending_transcript
                else self.audio_turn_id
            )
            await self._cancel_current(current_turn_id)
        if not self.upstream_available:
            await self._send_error("AUDIO_UNAVAILABLE", "语音服务暂不可用，请使用文字输入。")
            return
        self.audio_turn_id = turn_id.strip()
        self.audio_transcript_parts.clear()
        await self.qwen.clear_audio()
        await self._send_json({"type": "turn.accepted", "turn_id": self.audio_turn_id})

    async def _commit_audio(self, turn_id: str) -> None:
        if not self.audio_turn_id or turn_id.strip() != self.audio_turn_id:
            await self._send_error("INVALID_AUDIO_TURN", "当前没有可提交的录音。")
            return
        await self.qwen.commit_audio()

    async def _handle_completed_transcript(
        self,
        transcript: str,
        turn_id: str,
        upstream_item_id: str,
    ) -> None:
        try:
            understanding = await asyncio.to_thread(
                self.service.normalize_transcript,
                transcript,
                self.visitor_id,
                self.session_id,
            )
        except PermissionError as exc:
            await self._send_error("SESSION_FORBIDDEN", str(exc))
            return
        correction = understanding.correction
        if correction is None:
            return
        LOGGER.info(
            "voice_transcript_correction turn_id=%s level=%s applied=%s matched_count=%s",
            turn_id,
            correction.level,
            correction.corrected_text != correction.original_text,
            len(correction.matched_terms),
        )
        if correction.level == "low":
            self.pending_transcript = PendingTranscript(turn_id, upstream_item_id, understanding)
            await self._send_json(
                {
                    "type": "user.transcript.confirmation_required",
                    "turn_id": turn_id,
                    "text": correction.original_text,
                    "candidates": correction.candidates,
                }
            )
            return
        await self._accept_transcript(turn_id, upstream_item_id, understanding)

    async def _confirm_transcript(self, turn_id: str, text: str) -> None:
        pending = self.pending_transcript
        confirmed = text.strip()
        if pending is None or pending.turn_id != turn_id.strip() or not confirmed:
            await self._send_error("INVALID_TRANSCRIPT_CONFIRMATION", "当前没有可确认的转写。")
            return
        self.pending_transcript = None
        correction = pending.understanding.correction
        if correction is None:
            return
        use_cached_expansion = confirmed in correction.candidates
        confirmed_correction = type(correction)(
            correction.original_text,
            confirmed,
            "low",
            correction.score,
            correction.candidates,
            correction.matched_terms,
        )
        understanding = VoiceQuestionUnderstanding(
            normalized_question=confirmed,
            correction_confidence=correction.score,
            expanded_questions=(
                pending.understanding.expanded_questions if use_cached_expansion else None
            ),
            correction=confirmed_correction,
        )
        await self._accept_transcript(pending.turn_id, pending.upstream_item_id, understanding)

    async def _accept_transcript(
        self,
        turn_id: str,
        upstream_item_id: str,
        understanding: VoiceQuestionUnderstanding,
    ) -> None:
        correction = understanding.correction
        if correction is None:
            return
        await self._send_json(
            {
                "type": "user.transcript.done",
                "turn_id": turn_id,
                "text": correction.corrected_text,
                "correction": {
                    "applied": correction.corrected_text != correction.original_text,
                    "level": correction.level,
                    "matched_terms": correction.matched_terms,
                },
            }
        )
        user_item_id = upstream_item_id
        if correction.corrected_text != correction.original_text:
            if upstream_item_id:
                await self.qwen.delete_item(upstream_item_id)
            user_item_id = await self.qwen.inject_message("user", correction.corrected_text)
        await self._start_question(
            correction.corrected_text,
            turn_id,
            inject_user=False,
            user_item_id=user_item_id,
            expanded_questions=understanding.expanded_questions,
        )

    async def _cancel_current(self, requested_turn_id: str) -> None:
        turn_id = (
            self.pending.turn_id if self.pending
            else self.pending_transcript.turn_id if self.pending_transcript
            else self.audio_turn_id
        )
        if not turn_id:
            return
        if requested_turn_id and requested_turn_id != turn_id:
            return
        if self.upstream_available and self.pending:
            await self.qwen.cancel_response()
            if not self.pending.response_id:
                try:
                    await asyncio.wait_for(self.pending.response_created.wait(), timeout=0.75)
                except TimeoutError:
                    # Without a response ID, stale terminal events cannot be correlated safely.
                    self.upstream_available = False
        if self.upstream_available and self.audio_turn_id:
            await self.qwen.clear_audio()
        if self.upstream_available and self.pending_transcript and self.pending_transcript.upstream_item_id:
            await self.qwen.delete_item(self.pending_transcript.upstream_item_id)
        if self.pending and self.upstream_available:
            await self._delete_turn_items(self.pending)
        if self.pending and self.pending.response_id:
            self._stale_response_ids.add(self.pending.response_id)
        self.pending = None
        self.pending_transcript = None
        self.audio_turn_id = ""
        self.audio_transcript_parts.clear()
        await self._send_json(
            {"type": "turn.cancelled", "turn_id": turn_id, "reason": "client_cancelled"}
        )

    async def _finish_completed(self, event: dict[str, Any]) -> None:
        pending = await self._begin_finalization(_response_id(event))
        if pending is None:
            return
        answer = "".join(pending.answer_parts).strip() or _response_text(event)
        streamed_answer = answer
        fallback_message = ""
        if not answer:
            answer = await asyncio.to_thread(self.service.fallback_answer, pending.prepared)
            fallback_message = "实时回答未返回文本，已使用本地证据文本。"
        finalized = await asyncio.to_thread(
            self.service.finalize_answer,
            pending.prepared,
            answer,
            pending.mode,
        )
        answer = finalized.text
        try:
            await asyncio.to_thread(
                self.service.persist_completed,
                pending.prepared,
                answer,
                pending.turn_id,
            )
            if fallback_message:
                await self._replace_with_fallback_context(pending, answer)
                await self._send_json(
                    {
                        "type": "error",
                        "code": "TEXT_FALLBACK",
                        "message": fallback_message,
                        "recoverable": True,
                    }
                )
                await self._send_json(
                    {"type": "assistant.text.delta", "turn_id": pending.turn_id, "delta": answer}
                )
            else:
                await self._delete_evidence(pending)
                if finalized.appended_text:
                    # Stream only the deterministic suffix because the model portion was already forwarded live.
                    suffix = answer[len(streamed_answer):] if answer.startswith(streamed_answer) else finalized.appended_text
                    await self._send_json(
                        {"type": "assistant.text.delta", "turn_id": pending.turn_id, "delta": suffix}
                    )
            await self._send_json(
                {"type": "assistant.text.done", "turn_id": pending.turn_id, "text": answer}
            )
            if pending.audio_started:
                await self._send_json({"type": "assistant.audio.done", "turn_id": pending.turn_id})
            await self._send_json(
                {"type": "turn.completed", "turn_id": pending.turn_id, "session_id": self.session_id}
            )
        finally:
            self._finalization_done.set()

    async def _fallback_current(self, message: str) -> None:
        pending = await self._begin_finalization()
        if pending is None:
            return
        try:
            answer = await asyncio.to_thread(self.service.fallback_answer, pending.prepared)
            finalized = await asyncio.to_thread(
                self.service.finalize_answer,
                pending.prepared,
                answer,
                pending.mode,
            )
            answer = finalized.text
            await asyncio.to_thread(
                self.service.persist_completed,
                pending.prepared,
                answer,
                pending.turn_id,
            )
            await self._replace_with_fallback_context(pending, answer)
            await self._send_json(
                {"type": "error", "code": "TEXT_FALLBACK", "message": message, "recoverable": True}
            )
            await self._send_json(
                {"type": "assistant.text.delta", "turn_id": pending.turn_id, "delta": answer}
            )
            await self._send_json(
                {"type": "assistant.text.done", "turn_id": pending.turn_id, "text": answer}
            )
            await self._send_json(
                {"type": "turn.completed", "turn_id": pending.turn_id, "session_id": self.session_id}
            )
        finally:
            self._finalization_done.set()

    async def _finish_cancelled(self, reason: str, response_id: str = "") -> None:
        pending = await self._begin_finalization(response_id)
        if pending is None:
            return
        try:
            await self._delete_turn_items(pending)
            await self._send_json(
                {"type": "turn.cancelled", "turn_id": pending.turn_id, "reason": reason}
            )
        finally:
            self._finalization_done.set()

    async def _begin_finalization(self, response_id: str = "") -> PendingTurn | None:
        async with self._turn_transition_lock:
            if self.pending is None:
                return None
            if response_id and self.pending.response_id != response_id:
                return None
            pending = self.pending
            self.pending = None
            self._finalization_done.clear()
            return pending

    async def _browser_loop(self) -> None:
        while True:
            try:
                message = await self.browser.receive()
            except WebSocketDisconnect:
                return
            if message.get("type") == "websocket.disconnect":
                return
            if message.get("bytes") is not None:
                await self.handle_audio_frame(message["bytes"])
                continue
            raw_text = message.get("text")
            if raw_text is None:
                continue
            try:
                import json

                event = json.loads(raw_text)
            except (TypeError, ValueError):
                await self._send_error("INVALID_JSON", "客户端事件必须是 JSON。")
                continue
            await self.handle_client_event(event)

    async def _delete_evidence(self, pending: PendingTurn) -> None:
        if not pending.evidence_item_id or not self.upstream_available:
            return
        try:
            await self.qwen.delete_item(pending.evidence_item_id)
        except Exception:
            # Evidence is also discarded when the socket closes; cleanup must not hide a completed answer.
            return

    async def _delete_turn_items(self, pending: PendingTurn) -> None:
        for item_id in (
            pending.evidence_item_id,
            pending.user_item_id,
            pending.output_item_id,
        ):
            if not item_id:
                continue
            try:
                await self.qwen.delete_item(item_id)
            except Exception:
                # Closing the upstream socket is the final cleanup boundary for rejected deletions.
                continue

    async def _replace_with_fallback_context(
        self,
        pending: PendingTurn,
        answer: str,
    ) -> None:
        if not self.upstream_available:
            return
        await self._delete_turn_items(pending)
        try:
            # Reinsert the complete pair so upstream context matches the turn persisted in PostgreSQL.
            await self.qwen.inject_message("user", pending.prepared.question)
            await self.qwen.inject_message("assistant", answer)
        except Exception:
            return

    async def _send_json(self, event: dict[str, Any]) -> None:
        # 与 PCM 共用一把锁，形成有序单 writer，避免控制帧与音频帧交错。
        async with self._send_lock:
            await self.browser.send_json(event)

    async def _send_bytes(self, pcm: bytes) -> None:
        async with self._send_lock:
            await self.browser.send_bytes(pcm)

    async def _send_error(
        self,
        code: str,
        message: str,
        recoverable: bool = False,
    ) -> None:
        await self._send_json(
            {"type": "error", "code": code, "message": message, "recoverable": recoverable}
        )


def _event_text(event: dict[str, Any]) -> str:
    return str(event.get("delta") or event.get("text") or event.get("transcript") or "")


def _response_id(event: dict[str, Any]) -> str:
    return str(event.get("response_id") or (event.get("response") or {}).get("id") or "")


def _is_answer_delta(event_type: str, mode: str) -> bool:
    if mode == "avatar":
        return event_type in {
            "response.audio_transcript.delta",
            "response.output_audio_transcript.delta",
        }
    return event_type in {"response.text.delta", "response.output_text.delta"}


def _response_text(event: dict[str, Any]) -> str:
    response = event.get("response") or {}
    for output in response.get("output") or []:
        for content in output.get("content") or []:
            text = content.get("text") or content.get("transcript")
            if text:
                return str(text).strip()
    return ""
