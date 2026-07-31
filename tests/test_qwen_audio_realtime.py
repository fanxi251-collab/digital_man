import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest

from lingjing_ai.config.settings import AppSettings
from lingjing_ai.realtime.qwen_audio import (
    QwenAudioRealtimeClient,
    QwenRealtimeSessionConfig,
    QwenRealtimeError,
)


class FakeSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.events = [
            json.dumps({"type": "session.created", "session": {"id": "upstream_1"}}),
            json.dumps({
                "type": "session.updated",
                "session": {"id": "upstream_1", "voice": "longanlufeng"},
            }),
        ]

    async def send(self, payload: str) -> None:
        self.sent.append(payload)

    async def recv(self) -> str:
        return self.events.pop(0)

    async def close(self) -> None:
        return None


def test_realtime_client_initializes_text_only_and_injects_history(tmp_path: Path):
    socket = FakeSocket()
    settings = replace(
        AppSettings.for_workspace(tmp_path),
        llm_api_key="test-key",
        realtime_workspace_id="workspace_1",
    )

    async def connect(url: str, **kwargs):
        assert url == (
            "wss://workspace_1.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime"
            "?model=qwen-audio-3.0-realtime-flash"
        )
        assert kwargs["additional_headers"]["Authorization"] == "Bearer test-key"
        return socket

    client = QwenAudioRealtimeClient(settings, connect_factory=connect)
    asyncio.run(
        client.open(
            [
                {"role": "user", "content": "灵山胜境有什么特色？"},
                {"role": "assistant", "content": "灵山胜境以灵山大佛闻名。"},
            ],
            QwenRealtimeSessionConfig(
                voice="longanlufeng",
                instructions="男导游完整角色指令",
            ),
        )
    )

    events = [json.loads(payload) for payload in socket.sent]
    assert events[0] == {
        "type": "session.update",
        "session": {
            "modalities": ["text"],
            "voice": "longanlufeng",
            "instructions": "男导游完整角色指令",
            "max_history_turns": 6,
            "turn_detection": None,
        },
    }
    assert [event["item"]["role"] for event in events[1:]] == ["user", "assistant"]


def test_realtime_client_uses_explicit_modalities_for_each_mode(tmp_path: Path):
    socket = FakeSocket()
    settings = replace(AppSettings.for_workspace(tmp_path), llm_api_key="test-key")

    async def connect(url: str, **kwargs):
        return socket

    async def scenario():
        client = QwenAudioRealtimeClient(settings, connect_factory=connect)
        await client.open(
            [],
            QwenRealtimeSessionConfig("longanlufeng", "男导游完整角色指令"),
        )
        await client.create_response("text")
        await client.create_response("avatar")
        await client.append_audio(b"\x01\x02")
        await client.commit_audio()

    asyncio.run(scenario())

    events = [json.loads(payload) for payload in socket.sent]
    response_events = [event for event in events if event["type"] == "response.create"]
    assert response_events == [
        {"type": "response.create", "response": {"modalities": ["text"]}},
        {"type": "response.create", "response": {"modalities": ["audio", "text"]}},
    ]
    audio_event = next(event for event in events if event["type"] == "input_audio_buffer.append")
    assert audio_event["audio"] == "AQI="
    assert events[-1] == {"type": "input_audio_buffer.commit"}


def test_realtime_client_rejects_a_session_voice_mismatch(tmp_path: Path):
    socket = FakeSocket()
    settings = replace(AppSettings.for_workspace(tmp_path), llm_api_key="test-key")

    async def connect(url: str, **kwargs):
        return socket

    client = QwenAudioRealtimeClient(settings, connect_factory=connect)
    with pytest.raises(QwenRealtimeError, match="音色"):
        asyncio.run(
            client.open(
                [],
                QwenRealtimeSessionConfig("longanqian", "女导游完整角色指令"),
            )
        )
