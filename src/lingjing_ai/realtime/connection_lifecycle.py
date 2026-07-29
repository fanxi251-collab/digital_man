from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
from time import perf_counter
from typing import Any

from lingjing_ai.realtime.avatar_profiles import (
    build_avatar_session_instructions,
    resolve_avatar_profile,
)
from lingjing_ai.realtime.qwen_audio import (
    QwenAudioRealtimeClient,
    QwenRealtimeSessionConfig,
)


LOGGER = logging.getLogger(__name__)
RealtimeClientFactory = Callable[[], QwenAudioRealtimeClient]


class RealtimeConnectionLifecycle:
    """Own Qwen connection generations so conversation code cannot mix old-role events."""

    def _profile(self, avatar_id: str):
        profile = resolve_avatar_profile(self.settings, avatar_id)
        if profile is None:
            raise ValueError(f"不支持的数字人角色：{avatar_id}")
        return profile

    def _session_config(self, avatar_id: str) -> QwenRealtimeSessionConfig:
        profile = self._profile(avatar_id)
        return QwenRealtimeSessionConfig(
            voice=profile.voice,
            instructions=build_avatar_session_instructions(self.settings, profile),
        )

    def _start_upstream_task(self) -> None:
        if not self._run_started or not self.upstream_available:
            return
        generation = self._connection_generation
        client = self.qwen
        self._upstream_task = asyncio.create_task(
            self._upstream_loop(client, generation)
        )

    async def _stop_upstream_task(self) -> None:
        task = self._upstream_task
        self._upstream_task = None
        if task is None or task is asyncio.current_task():
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def _reject_during_avatar_switch(self) -> bool:
        if not self._avatar_switching:
            return False
        await self._send_error(
            "AVATAR_SWITCH_IN_PROGRESS",
            "数字人角色正在切换，请稍候再提交。",
            recoverable=True,
        )
        return True

    async def _switch_avatar(self, requested_avatar_id: str) -> None:
        async with self._avatar_switch_lock:
            profile = self._profile(requested_avatar_id)
            if requested_avatar_id == self.avatar_id:
                await self._send_json(
                    {
                        "type": "avatar.changed",
                        "avatar_id": self.avatar_id,
                        "voice": profile.voice,
                    }
                )
                return

            started_at = perf_counter()
            active_avatar_id = self.avatar_id
            old_client = self.qwen
            old_available = self.upstream_available
            candidate: QwenAudioRealtimeClient | None = None
            self._avatar_switching = True
            try:
                if self.pending or self.pending_transcript or self.audio_turn_id:
                    await self._cancel_current("")
                await self._send_json(
                    {
                        "type": "avatar.changing",
                        "active_avatar_id": active_avatar_id,
                        "requested_avatar_id": requested_avatar_id,
                    }
                )
                await self._stop_upstream_task()
                if self._qwen_client_factory is None:
                    raise RuntimeError("实时客户端工厂不可用，无法安全重建角色连接。")
                candidate = self._qwen_client_factory()
                if candidate is old_client:
                    raise RuntimeError("角色切换必须创建独立的上游连接。")
                history = await asyncio.to_thread(
                    self.service.upstream_history,
                    self.session_id,
                    self.visitor_id,
                )
                async with asyncio.timeout(
                    self.settings.realtime_connect_timeout_seconds
                ):
                    await candidate.open(
                        history,
                        self._session_config(requested_avatar_id),
                    )

                self.qwen = candidate
                self.avatar_id = requested_avatar_id
                self.upstream_available = True
                # 角色切换成功后允许后续断线再次进入重连预算。
                self._reconnect_failures = 0
                self._connection_generation += 1
                self._start_upstream_task()
                await old_client.close()
                await self._send_json(
                    {
                        "type": "avatar.changed",
                        "avatar_id": requested_avatar_id,
                        "voice": profile.voice,
                    }
                )
                LOGGER.info(
                    "avatar_connection_switch from=%s to=%s voice=%s generation=%s latency_ms=%s status=ok",
                    active_avatar_id,
                    requested_avatar_id,
                    profile.voice,
                    self._connection_generation,
                    round((perf_counter() - started_at) * 1000),
                )
            except Exception as exc:
                if candidate is not None and candidate is not old_client:
                    try:
                        await candidate.close()
                    except Exception:
                        pass
                self.qwen = old_client
                self.avatar_id = active_avatar_id
                self.upstream_available = old_available
                self._start_upstream_task()
                await self._send_json(
                    {
                        "type": "avatar.change_failed",
                        "active_avatar_id": active_avatar_id,
                        "requested_avatar_id": requested_avatar_id,
                        "code": "AVATAR_CONNECT_FAILED",
                        "message": str(exc),
                        "upstream_available": old_available,
                    }
                )
                LOGGER.warning(
                    "avatar_connection_switch from=%s to=%s voice=%s latency_ms=%s status=failed error=%s",
                    active_avatar_id,
                    requested_avatar_id,
                    profile.voice,
                    round((perf_counter() - started_at) * 1000),
                    type(exc).__name__,
                )
            finally:
                self._avatar_switching = False

    async def _upstream_loop(
        self,
        client: QwenAudioRealtimeClient,
        generation: int,
    ) -> None:
        while True:
            try:
                event = await client.receive_event()
                if generation != self._connection_generation or client is not self.qwen:
                    return
                await self.handle_upstream_event(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if (
                    generation == self._connection_generation
                    and client is self.qwen
                    and await self._try_reconnect(client)
                ):
                    return
                await self._send_error("UPSTREAM_DISCONNECTED", str(exc), recoverable=True)
                self.upstream_available = False
                await self._fallback_current("语音模型连接中断，已使用本地证据文本。")
                return

    async def _try_reconnect(self, disconnected_client: QwenAudioRealtimeClient) -> bool:
        max_attempts = max(1, int(self.settings.realtime_reconnect_max_attempts))
        base_delay_ms = max(0, int(self.settings.realtime_reconnect_base_delay_ms))
        try:
            await disconnected_client.close()
        except Exception:
            pass

        last_error: Exception | None = None
        for attempt in range(max_attempts):
            if attempt > 0 and base_delay_ms > 0:
                # 指数退避：第 2 次起等待 base * 2^(n-1)，降低上游抖动时的重试风暴。
                delay_seconds = (base_delay_ms / 1000.0) * (2 ** (attempt - 1))
                await asyncio.sleep(delay_seconds)

            replacement = disconnected_client
            try:
                history = await asyncio.to_thread(
                    self.service.upstream_history,
                    self.session_id,
                    self.visitor_id,
                )
                if self._qwen_client_factory is not None:
                    replacement = self._qwen_client_factory()
                await replacement.open(history, self._session_config(self.avatar_id))
                self.qwen = replacement
                self.upstream_available = True
                self._reconnect_failures = 0
                self._connection_generation += 1
                if self.pending:
                    await self._send_json(
                        {"type": "turn.reset", "turn_id": self.pending.turn_id}
                    )
                    self.pending.answer_parts.clear()
                    self.pending.audio_started = False
                    self.pending.response_id = ""
                    self.pending.response_created = asyncio.Event()
                    self.pending.output_item_id = ""
                    self.pending.user_item_id = await replacement.inject_message(
                        "user", self.pending.prepared.question
                    )
                    self.pending.evidence_item_id = await replacement.inject_evidence(
                        self.pending.prepared.evidence_prompt
                    )
                    await replacement.create_response(self.pending.mode)
                elif self.audio_turn_id:
                    turn_id = self.audio_turn_id
                    self.audio_turn_id = ""
                    self.audio_transcript_parts.clear()
                    await self._send_json(
                        {"type": "turn.cancelled", "turn_id": turn_id, "reason": "audio_reconnect"}
                    )
                self._start_upstream_task()
                LOGGER.info(
                    "upstream_reconnect attempt=%s/%s status=ok generation=%s",
                    attempt + 1,
                    max_attempts,
                    self._connection_generation,
                )
                return True
            except Exception as exc:
                last_error = exc
                self._reconnect_failures = attempt + 1
                if replacement is not disconnected_client:
                    try:
                        await replacement.close()
                    except Exception:
                        pass
                LOGGER.warning(
                    "upstream_reconnect attempt=%s/%s status=failed error=%s",
                    attempt + 1,
                    max_attempts,
                    type(exc).__name__,
                )

        if last_error is not None:
            LOGGER.error(
                "upstream_reconnect exhausted attempts=%s last_error=%s",
                max_attempts,
                type(last_error).__name__,
            )
        return False
