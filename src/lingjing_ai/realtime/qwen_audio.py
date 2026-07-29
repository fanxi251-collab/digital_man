from __future__ import annotations

import base64
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
import uuid

import websockets

from lingjing_ai.config.settings import AppSettings


ConnectFactory = Callable[..., Awaitable[Any]]


class QwenRealtimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class QwenRealtimeSessionConfig:
    voice: str
    instructions: str


class QwenAudioRealtimeClient:
    def __init__(
        self,
        settings: AppSettings,
        connect_factory: ConnectFactory | None = None,
    ) -> None:
        self.settings = settings
        self.connect_factory = connect_factory or websockets.connect
        self.socket: Any | None = None

    @property
    def endpoint(self) -> str:
        if self.settings.realtime_url:
            return self.settings.realtime_url
        if self.settings.realtime_workspace_id:
            host = f"{self.settings.realtime_workspace_id}.cn-beijing.maas.aliyuncs.com"
        else:
            host = "dashscope.aliyuncs.com"
        return f"wss://{host}/api-ws/v1/realtime?model={self.settings.realtime_model}"

    async def open(
        self,
        history: list[dict[str, str]],
        session_config: QwenRealtimeSessionConfig | None = None,
    ) -> None:
        if not self.settings.llm_api_key:
            raise QwenRealtimeError("未配置 LJAPI_KEY，无法连接实时语音模型。")
        config = session_config or QwenRealtimeSessionConfig(
            voice=self.settings.realtime_voice,
            instructions=self.settings.realtime_instructions,
        )
        self.socket = await self.connect_factory(
            self.endpoint,
            additional_headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
            open_timeout=self.settings.realtime_connect_timeout_seconds,
            close_timeout=3,
            max_size=None,
        )
        created = await self.receive_event()
        if created.get("type") != "session.created":
            raise QwenRealtimeError("Qwen 实时会话未返回 session.created。")
        await self.send_event(
            {
                "type": "session.update",
                "session": {
                    "modalities": ["text"],
                    "voice": config.voice,
                    "instructions": config.instructions,
                    "max_history_turns": self.settings.realtime_history_turns,
                    "turn_detection": None,
                },
            }
        )
        updated = await self.receive_event()
        if updated.get("type") != "session.updated":
            raise QwenRealtimeError("Qwen 实时会话配置失败。")
        actual_voice = str((updated.get("session") or {}).get("voice") or "").strip()
        if actual_voice != config.voice:
            await self.close()
            raise QwenRealtimeError(
                f"Qwen 实时会话音色不一致：请求 {config.voice}，实际 {actual_voice}。"
            )
        for message in history[-self.settings.realtime_history_turns * 2 :]:
            await self.inject_message(message.get("role", "user"), message.get("content", ""))

    async def close(self) -> None:
        if self.socket is not None:
            await self.socket.close()
            self.socket = None

    async def send_event(self, event: dict[str, Any]) -> None:
        if self.socket is None:
            raise QwenRealtimeError("Qwen 实时会话尚未连接。")
        await self.socket.send(json.dumps(event, ensure_ascii=False))

    async def receive_event(self) -> dict[str, Any]:
        if self.socket is None:
            raise QwenRealtimeError("Qwen 实时会话尚未连接。")
        raw = await self.socket.recv()
        if not isinstance(raw, str):
            raise QwenRealtimeError("Qwen 返回了无法识别的二进制控制事件。")
        return json.loads(raw)

    async def inject_message(self, role: str, content: str, item_id: str | None = None) -> str:
        normalized_role = role if role in {"system", "user", "assistant"} else "user"
        content_type = "output_text" if normalized_role == "assistant" else "input_text"
        resolved_id = item_id or f"item_{uuid.uuid4().hex}"
        await self.send_event(
            {
                "type": "conversation.item.create",
                "item": {
                    "id": resolved_id,
                    "type": "message",
                    "role": normalized_role,
                    "content": [{"type": content_type, "text": content}],
                },
            }
        )
        return resolved_id

    async def inject_evidence(self, content: str) -> str:
        return await self.inject_message("system", content, f"evidence_{uuid.uuid4().hex}")

    async def delete_item(self, item_id: str) -> None:
        await self.send_event({"type": "conversation.item.delete", "item_id": item_id})

    async def append_audio(self, pcm: bytes) -> None:
        await self.send_event(
            {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(pcm).decode("ascii"),
            }
        )

    async def commit_audio(self) -> None:
        await self.send_event({"type": "input_audio_buffer.commit"})

    async def clear_audio(self) -> None:
        await self.send_event({"type": "input_audio_buffer.clear"})

    async def create_response(self, mode: str) -> None:
        modalities = ["audio", "text"] if mode == "avatar" else ["text"]
        # Voice is connection-scoped by Qwen, so per-turn requests only control output modalities.
        await self.send_event(
            {"type": "response.create", "response": {"modalities": modalities}}
        )

    async def cancel_response(self) -> None:
        await self.send_event({"type": "response.cancel"})
