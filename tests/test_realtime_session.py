import asyncio
import base64
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from lingjing_ai.agent.models import AgentEvidence
from lingjing_ai.config.settings import AppSettings
from lingjing_ai.realtime.answer_contract import build_answer_contract, finalize_answer
from lingjing_ai.realtime.session import VisitorRealtimeSession
from lingjing_ai.realtime.transcript import TranscriptCorrection
from lingjing_ai.services.question_expansion import VoiceQuestionUnderstanding
from lingjing_ai.services.conversation_store import ConversationSessionRecord


class FakeBrowser:
    def __init__(self) -> None:
        self.json_events = []
        self.audio_frames = []

    async def send_json(self, event):
        self.json_events.append(event)

    async def send_bytes(self, pcm):
        self.audio_frames.append(pcm)


class FakeQwen:
    def __init__(self, fail_open: bool = False) -> None:
        self.history = []
        self.session_configs = []
        self.messages = []
        self.evidence_items = []
        self.deleted = []
        self.responses = []
        self.audio = []
        self.commits = 0
        self.cancels = 0
        self.fail_create_response = False
        self.fail_open = fail_open
        self.close_count = 0

    async def open(self, history, session_config=None):
        if self.fail_open:
            raise RuntimeError("candidate connection failed")
        self.history = history
        self.session_configs.append(session_config)

    async def close(self):
        self.close_count += 1

    async def inject_message(self, role, content, item_id=None):
        self.messages.append((role, content))
        return item_id or "message_1"

    async def inject_evidence(self, content):
        self.evidence_items.append(content)
        return "evidence_1"

    async def delete_item(self, item_id):
        self.deleted.append(item_id)

    async def create_response(self, mode):
        if self.fail_create_response:
            raise RuntimeError("upstream create failed")
        self.responses.append(mode)

    async def append_audio(self, pcm):
        self.audio.append(pcm)

    async def commit_audio(self):
        self.commits += 1

    async def clear_audio(self):
        return None

    async def cancel_response(self):
        self.cancels += 1


class FakeConversationService:
    def __init__(self) -> None:
        self.history = []
        self.persisted = []
        self.prepare_calls = []
        self.prepare_styles = []
        self.normalize_calls = []
        self.voice_understanding = VoiceQuestionUnderstanding(
            correction=TranscriptCorrection("", "", "none", 0, [], []),
            expanded_questions=[],
        )
        self.prepared = SimpleNamespace(
            session=ConversationSessionRecord(
                "sess_1", "visitor_a", "灵山问题", "灵山问题", "now", "now"
            ),
            question="灵山胜境有什么特色？",
            evidence=AgentEvidence(
                question="灵山胜境有什么特色？",
                sources=[],
                confidence=0.5,
                is_answered=True,
                trace_id="trace_1",
                tool_trace=[],
            ),
            evidence_prompt="临时证据：灵山胜境资料",
            source_payloads=[],
            tool_trace_payloads=[],
            context_summary="",
            persisted=False,
        )

    def upstream_history(self, session_id, visitor_id):
        return self.history

    def normalize_transcript(self, question, visitor_id, session_id):
        self.normalize_calls.append(question)
        correction = self.voice_understanding.correction
        if not correction.original_text:
            correction = TranscriptCorrection(question, question, "none", 0, [], [])
        return VoiceQuestionUnderstanding(
            normalized_question=correction.corrected_text,
            correction_confidence=correction.score,
            expanded_questions=self.voice_understanding.expanded_questions,
            correction=correction,
        )

    def prepare_turn(
        self,
        question,
        visitor_id,
        session_id,
        expanded_questions=None,
        mode="text",
        avatar_style="",
    ):
        self.prepare_calls.append((question, expanded_questions, mode))
        self.prepare_styles.append(avatar_style)
        self.prepared.question = question
        return self.prepared

    def finalize_answer(self, prepared, answer, mode):
        route_error = getattr(getattr(prepared, "answer_contract", None), "route_error", "")
        if route_error:
            return SimpleNamespace(
                text=f"路线查询失败：{route_error}。请稍后重试或核对起点和终点。",
                appended_text="",
            )
        if answer == "路线简答" and mode == "text":
            return SimpleNamespace(text="路线简答\n\n完整路线块", appended_text="\n\n完整路线块")
        return SimpleNamespace(text=answer, appended_text="")

    def persist_completed(self, prepared, answer, turn_id=""):
        self.persisted.append((prepared.question, answer))

    def fallback_answer(self, prepared):
        return "本地证据兜底回答"


def test_text_mode_requests_text_only_and_persists_complete_answer(tmp_path: Path):
    async def scenario():
        browser = FakeBrowser()
        qwen = FakeQwen()
        service = FakeConversationService()
        session = VisitorRealtimeSession(
            browser,
            "visitor_a",
            "",
            AppSettings.for_workspace(tmp_path),
            service,
            qwen,
        )
        await session.open()
        await session.handle_client_event(
            {"type": "text.submit", "turn_id": "turn_1", "text": "灵山胜境有什么特色？"}
        )
        await session.handle_upstream_event({"type": "response.text.delta", "delta": "灵山"})
        await session.handle_upstream_event({"type": "response.text.delta", "delta": "值得游览。"})
        await session.handle_upstream_event({"type": "response.done", "response": {"status": "completed"}})
        return browser, qwen, service

    browser, qwen, service = asyncio.run(scenario())

    assert qwen.responses == ["text"]
    assert qwen.messages == [("user", "灵山胜境有什么特色？")]
    assert service.persisted == [("灵山胜境有什么特色？", "灵山值得游览。")]
    assert qwen.deleted == ["evidence_1"]
    assert browser.json_events[-1]["type"] == "turn.completed"


def test_initial_male_avatar_configures_the_first_upstream_session(tmp_path: Path):
    async def scenario():
        browser = FakeBrowser()
        qwen = FakeQwen()
        session = VisitorRealtimeSession(
            browser,
            "visitor_a",
            "",
            AppSettings.for_workspace(tmp_path),
            FakeConversationService(),
            qwen,
            avatar_id="chitose",
        )
        await session.open()
        return browser, qwen

    browser, qwen = asyncio.run(scenario())

    assert qwen.session_configs[0].voice == "longanlufeng"
    assert "Chitose男导游" in qwen.session_configs[0].instructions
    ready = next(event for event in browser.json_events if event["type"] == "session.ready")
    assert ready["avatar_id"] == "chitose"
    assert ready["voice"] == "longanlufeng"


def test_text_mode_replaces_streamed_markdown_with_clean_final_and_history_text(tmp_path: Path):
    async def scenario():
        browser = FakeBrowser()
        qwen = FakeQwen()
        service = FakeConversationService()
        service.prepared.answer_contract = build_answer_contract(service.prepared.evidence, "avatar")

        def finalize_with_contract(prepared, answer, mode):
            return finalize_answer(prepared.evidence, prepared.answer_contract, answer)

        service.finalize_answer = finalize_with_contract
        session = VisitorRealtimeSession(
            browser,
            "visitor_a",
            "",
            AppSettings.for_workspace(tmp_path),
            service,
            qwen,
        )
        await session.open()
        await session.handle_client_event(
            {"type": "text.submit", "turn_id": "turn_markdown", "text": "给我游览建议"}
        )
        await session.handle_upstream_event(
            {"type": "response.text.delta", "delta": "**游览建议**：提前确认开放时间。"}
        )
        await session.handle_upstream_event(
            {"type": "response.done", "response": {"status": "completed"}}
        )
        return browser, service

    browser, service = asyncio.run(scenario())

    done = next(event for event in browser.json_events if event["type"] == "assistant.text.done")
    assert done["text"] == "游览建议：提前确认开放时间。"
    assert service.persisted == [("给我游览建议", "游览建议：提前确认开放时间。")]


def test_text_mode_streams_and_persists_deterministic_route_completion(tmp_path: Path):
    async def scenario():
        browser = FakeBrowser()
        qwen = FakeQwen()
        service = FakeConversationService()
        session = VisitorRealtimeSession(
            browser,
            "visitor_a",
            "",
            AppSettings.for_workspace(tmp_path),
            service,
            qwen,
        )
        await session.open()
        await session.handle_client_event(
            {"type": "text.submit", "turn_id": "turn_route", "text": "从无锡站到灵山胜境怎么走？"}
        )
        await session.handle_upstream_event({"type": "response.text.delta", "delta": "路线简答"})
        await session.handle_upstream_event({"type": "response.done", "response": {"status": "completed"}})
        return browser, service

    browser, service = asyncio.run(scenario())

    appended = [
        event for event in browser.json_events
        if event["type"] == "assistant.text.delta" and "完整路线块" in event.get("delta", "")
    ]
    assert len(appended) == 1
    assert service.persisted == [("从无锡站到灵山胜境怎么走？", "路线简答\n\n完整路线块")]
    done = next(event for event in browser.json_events if event["type"] == "assistant.text.done")
    assert done["text"] == "路线简答\n\n完整路线块"


def test_route_tool_failure_uses_deterministic_text_without_creating_qwen_response(tmp_path: Path):
    async def scenario():
        browser = FakeBrowser()
        qwen = FakeQwen()
        service = FakeConversationService()
        service.prepared.answer_contract = SimpleNamespace(route_error="高德请求超时")
        session = VisitorRealtimeSession(
            browser, "visitor_a", "", AppSettings.for_workspace(tmp_path), service, qwen
        )
        await session.open()
        await session.handle_client_event(
            {"type": "text.submit", "turn_id": "turn_failed_route", "text": "从无锡站到灵山胜境怎么走？"}
        )
        return browser, qwen, service

    browser, qwen, service = asyncio.run(scenario())

    assert qwen.responses == []
    assert service.persisted == [
        (
            "从无锡站到灵山胜境怎么走？",
            "路线查询失败：高德请求超时。请稍后重试或核对起点和终点。",
        )
    ]
    assert any(event["type"] == "turn.completed" for event in browser.json_events)


def test_avatar_audio_flow_forwards_pcm_and_audio_output(tmp_path: Path):
    async def scenario():
        browser = FakeBrowser()
        qwen = FakeQwen()
        service = FakeConversationService()
        session = VisitorRealtimeSession(
            browser,
            "visitor_a",
            "sess_1",
            AppSettings.for_workspace(tmp_path),
            service,
            qwen,
        )
        await session.open()
        await session.handle_client_event({"type": "mode.set", "mode": "avatar"})
        await session.handle_client_event({"type": "audio.start", "turn_id": "turn_audio"})
        await session.handle_audio_frame(b"\x01\x02")
        await session.handle_client_event({"type": "audio.commit", "turn_id": "turn_audio"})
        await session.handle_upstream_event(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "transcript": "灵山胜境有什么特色？",
            }
        )
        await session.handle_upstream_event(
            {"type": "response.audio_transcript.delta", "delta": "灵山很美。"}
        )
        await session.handle_upstream_event(
            {"type": "response.audio.delta", "delta": base64.b64encode(b"\x03\x04").decode()}
        )
        await session.handle_upstream_event({"type": "response.done", "response": {"status": "completed"}})
        return browser, qwen

    browser, qwen = asyncio.run(scenario())

    assert qwen.audio == [b"\x01\x02"]
    assert qwen.commits == 1
    assert qwen.responses == ["avatar"]
    assert browser.audio_frames == [b"\x03\x04"]
    assert any(event["type"] == "user.transcript.done" for event in browser.json_events)
    assert any(event["type"] == "assistant.audio.started" for event in browser.json_events)


def test_avatar_selection_is_whitelisted_and_controls_voice_and_style(tmp_path: Path):
    async def scenario():
        browser = FakeBrowser()
        qwen = FakeQwen()
        male_qwen = FakeQwen()
        service = FakeConversationService()
        session = VisitorRealtimeSession(
            browser,
            "visitor_a",
            "",
            AppSettings.for_workspace(tmp_path),
            service,
            qwen,
            qwen_client_factory=lambda: male_qwen,
        )
        await session.open()
        await session.handle_client_event({"type": "avatar.set", "avatar_id": "haruto"})
        await session.handle_client_event({"type": "avatar.set", "avatar_id": "chitose"})
        await session.handle_client_event({"type": "mode.set", "mode": "avatar"})
        await session.handle_client_event(
            {"type": "text.submit", "turn_id": "turn_male", "text": "介绍一下灵山胜境"}
        )
        return browser, qwen, male_qwen, service, session

    browser, qwen, male_qwen, service, session = asyncio.run(scenario())

    ready = next(event for event in browser.json_events if event["type"] == "session.ready")
    assert ready["avatar_id"] == "mao_pro"
    assert any(
        event["type"] == "error" and event["code"] == "INVALID_AVATAR"
        for event in browser.json_events
    )
    assert any(
        event["type"] == "avatar.changed" and event["avatar_id"] == "chitose"
        for event in browser.json_events
    )
    assert session.pending.avatar_id == "chitose"
    assert qwen.close_count == 1
    assert male_qwen.responses == ["avatar"]
    assert male_qwen.session_configs[-1].voice == "longanlufeng"
    assert "沉稳" in male_qwen.session_configs[-1].instructions
    assert service.prepare_styles[-1] == ""


def test_switching_avatar_cancels_active_turn_before_acknowledging_new_avatar(tmp_path: Path):
    async def scenario():
        browser = FakeBrowser()
        qwen = FakeQwen()
        male_qwen = FakeQwen()
        service = FakeConversationService()
        session = VisitorRealtimeSession(
            browser,
            "visitor_a",
            "",
            AppSettings.for_workspace(tmp_path),
            service,
            qwen,
            qwen_client_factory=lambda: male_qwen,
        )
        await session.open()
        await session.handle_client_event({"type": "mode.set", "mode": "avatar"})
        await session.handle_client_event(
            {"type": "text.submit", "turn_id": "turn_old", "text": "介绍一下灵山胜境"}
        )
        await session.handle_upstream_event(
            {"type": "response.created", "response": {"id": "resp_old"}}
        )
        await session.handle_client_event({"type": "avatar.set", "avatar_id": "chitose"})
        return browser, qwen, male_qwen, service, session

    browser, qwen, male_qwen, service, session = asyncio.run(scenario())

    assert qwen.cancels == 1
    assert service.persisted == []
    assert session.pending is None
    assert session.avatar_id == "chitose"
    assert male_qwen.session_configs[-1].voice == "longanlufeng"
    assert browser.json_events[-1] == {
        "type": "avatar.changed",
        "avatar_id": "chitose",
        "voice": "longanlufeng",
    }


def test_failed_avatar_connection_keeps_old_role_and_connection(tmp_path: Path):
    async def scenario():
        browser = FakeBrowser()
        original = FakeQwen()
        failed = FakeQwen(fail_open=True)
        service = FakeConversationService()
        session = VisitorRealtimeSession(
            browser,
            "visitor_a",
            "",
            AppSettings.for_workspace(tmp_path),
            service,
            original,
            qwen_client_factory=lambda: failed,
        )
        await session.open()
        await session.handle_client_event({"type": "avatar.set", "avatar_id": "chitose"})
        return browser, original, failed, session

    browser, original, failed, session = asyncio.run(scenario())

    assert session.avatar_id == "mao_pro"
    assert session.qwen is original
    assert original.close_count == 0
    assert failed.close_count == 1
    assert browser.json_events[-1]["type"] == "avatar.change_failed"
    assert browser.json_events[-1]["active_avatar_id"] == "mao_pro"


def test_avatar_voice_mismatch_cancels_audio_and_uses_text_fallback(tmp_path: Path):
    async def scenario():
        browser = FakeBrowser()
        qwen = FakeQwen()
        service = FakeConversationService()
        session = VisitorRealtimeSession(
            browser,
            "visitor_a",
            "",
            AppSettings.for_workspace(tmp_path),
            service,
            qwen,
            avatar_id="chitose",
        )
        await session.open()
        await session.handle_client_event({"type": "mode.set", "mode": "avatar"})
        await session.handle_client_event(
            {"type": "text.submit", "turn_id": "turn_voice", "text": "介绍灵山胜境"}
        )
        await session.handle_upstream_event(
            {
                "type": "response.created",
                "response": {"id": "resp_voice", "voice": "longanqian"},
            }
        )
        return browser, qwen, service

    browser, qwen, service = asyncio.run(scenario())

    assert qwen.cancels == 1
    assert browser.audio_frames == []
    assert any(
        event["type"] == "error" and event["code"] == "AVATAR_VOICE_MISMATCH"
        for event in browser.json_events
    )
    assert service.persisted == [("介绍灵山胜境", "本地证据兜底回答")]


def test_medium_voice_correction_replaces_upstream_item_and_persists_only_corrected_text(
    tmp_path: Path, caplog
):
    caplog.set_level("INFO")
    async def scenario():
        browser = FakeBrowser()
        qwen = FakeQwen()
        service = FakeConversationService()
        service.voice_understanding = VoiceQuestionUnderstanding(
            correction=TranscriptCorrection(
                "源头主几点开放", "鼋头渚几点开放", "medium", 0.82,
                ["鼋头渚几点开放"], ["鼋头渚"],
            ),
            expanded_questions=["鼋头渚开放时间"],
        )
        session = VisitorRealtimeSession(
            browser, "visitor_a", "", AppSettings.for_workspace(tmp_path), service, qwen
        )
        await session.open()
        await session.handle_client_event({"type": "mode.set", "mode": "avatar"})
        await session.handle_client_event({"type": "audio.start", "turn_id": "turn_voice"})
        await session.handle_upstream_event({
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "源头主几点开放",
            "item_id": "audio_item_1",
        })
        await session.handle_upstream_event(
            {"type": "response.audio_transcript.delta", "delta": "开放时间见公告。"}
        )
        await session.handle_upstream_event(
            {"type": "response.done", "response": {"status": "completed"}}
        )
        return browser, qwen, service

    browser, qwen, service = asyncio.run(scenario())

    transcript = next(event for event in browser.json_events if event["type"] == "user.transcript.done")
    assert transcript["text"] == "鼋头渚几点开放"
    assert transcript["correction"]["level"] == "medium"
    assert qwen.deleted[0] == "audio_item_1"
    assert qwen.messages[0] == ("user", "鼋头渚几点开放")
    assert service.prepare_calls == [("鼋头渚几点开放", ["鼋头渚开放时间"], "avatar")]
    assert service.persisted == [("鼋头渚几点开放", "开放时间见公告。")]
    assert "turn_id=turn_voice" in caplog.text
    assert "level=medium" in caplog.text
    assert "源头主几点开放" not in caplog.text


def test_low_confidence_voice_waits_for_confirmation_before_preparing_turn(tmp_path: Path):
    async def scenario():
        browser = FakeBrowser()
        qwen = FakeQwen()
        service = FakeConversationService()
        service.voice_understanding = VoiceQuestionUnderstanding(
            correction=TranscriptCorrection(
                "年华玩怎么去", "拈花湾怎么去", "low", 0.71,
                ["拈花湾怎么去", "年华湾怎么去"], ["拈花湾"],
            ),
            expanded_questions=["拈花湾交通路线"],
        )
        session = VisitorRealtimeSession(
            browser, "visitor_a", "", AppSettings.for_workspace(tmp_path), service, qwen
        )
        await session.open()
        await session.handle_client_event({"type": "mode.set", "mode": "avatar"})
        await session.handle_client_event({"type": "audio.start", "turn_id": "turn_confirm"})
        await session.handle_upstream_event({
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "年华玩怎么去",
            "item_id": "audio_item_2",
        })
        before_confirm = list(service.prepare_calls)
        await session.handle_client_event({
            "type": "transcript.confirm", "turn_id": "turn_confirm", "text": "拈花湾怎么去"
        })
        return browser, qwen, service, before_confirm

    browser, qwen, service, before_confirm = asyncio.run(scenario())

    assert before_confirm == []
    confirmation = next(
        event for event in browser.json_events
        if event["type"] == "user.transcript.confirmation_required"
    )
    assert confirmation["candidates"] == ["拈花湾怎么去", "年华湾怎么去"]
    assert service.prepare_calls == [("拈花湾怎么去", ["拈花湾交通路线"], "avatar")]
    assert qwen.deleted[0] == "audio_item_2"
    assert qwen.messages[0] == ("user", "拈花湾怎么去")


def test_manually_edited_confirmation_requests_fresh_question_expansion(tmp_path: Path):
    async def scenario():
        browser = FakeBrowser()
        qwen = FakeQwen()
        service = FakeConversationService()
        service.voice_understanding = VoiceQuestionUnderstanding(
            correction=TranscriptCorrection(
                "年华玩怎么去", "拈花湾怎么去", "low", 0.71,
                ["拈花湾怎么去"], ["拈花湾"],
            ),
            expanded_questions=["拈花湾交通路线"],
        )
        session = VisitorRealtimeSession(
            browser, "visitor_a", "", AppSettings.for_workspace(tmp_path), service, qwen
        )
        await session.open()
        await session.handle_client_event({"type": "mode.set", "mode": "avatar"})
        await session.handle_client_event({"type": "audio.start", "turn_id": "turn_edit"})
        await session.handle_upstream_event({
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "年华玩怎么去",
            "item_id": "audio_item_edit",
        })
        await session.handle_client_event({
            "type": "transcript.confirm", "turn_id": "turn_edit", "text": "从无锡站到拈花湾怎么去"
        })
        return service

    service = asyncio.run(scenario())

    assert service.prepare_calls == [("从无锡站到拈花湾怎么去", None, "avatar")]


def test_cancel_does_not_persist_partial_answer(tmp_path: Path):
    async def scenario():
        browser = FakeBrowser()
        qwen = FakeQwen()
        service = FakeConversationService()
        session = VisitorRealtimeSession(
            browser,
            "visitor_a",
            "",
            AppSettings.for_workspace(tmp_path),
            service,
            qwen,
        )
        await session.open()
        await session.handle_client_event(
            {"type": "text.submit", "turn_id": "turn_1", "text": "灵山胜境有什么特色？"}
        )
        await session.handle_upstream_event({"type": "response.text.delta", "delta": "半截"})
        await session.handle_client_event({"type": "response.cancel", "turn_id": "turn_1"})
        return browser, qwen, service

    browser, qwen, service = asyncio.run(scenario())

    assert qwen.cancels == 1
    assert service.persisted == []
    assert browser.json_events[-1]["type"] == "turn.cancelled"


def test_upstream_send_failure_uses_local_text_fallback(tmp_path: Path):
    async def scenario():
        browser = FakeBrowser()
        qwen = FakeQwen()
        qwen.fail_create_response = True
        service = FakeConversationService()
        session = VisitorRealtimeSession(
            browser,
            "visitor_a",
            "",
            AppSettings.for_workspace(tmp_path),
            service,
            qwen,
        )
        await session.open()
        await session.handle_client_event(
            {"type": "text.submit", "turn_id": "turn_1", "text": "灵山胜境有什么特色？"}
        )
        return browser, service

    browser, service = asyncio.run(scenario())

    assert service.persisted == [("灵山胜境有什么特色？", "本地证据兜底回答")]
    assert browser.json_events[-1]["type"] == "turn.completed"


def test_late_events_from_cancelled_turn_cannot_complete_new_turn(tmp_path: Path):
    async def scenario():
        browser = FakeBrowser()
        qwen = FakeQwen()
        service = FakeConversationService()
        session = VisitorRealtimeSession(
            browser, "visitor_a", "", AppSettings.for_workspace(tmp_path), service, qwen
        )
        await session.open()
        await session.handle_client_event(
            {"type": "text.submit", "turn_id": "turn_1", "text": "第一个问题"}
        )
        await session.handle_upstream_event(
            {"type": "response.created", "response": {"id": "resp_1"}}
        )
        await session.handle_client_event(
            {"type": "text.submit", "turn_id": "turn_2", "text": "第二个问题"}
        )
        await session.handle_upstream_event(
            {"type": "response.created", "response": {"id": "resp_2"}}
        )
        await session.handle_upstream_event(
            {
                "type": "error",
                "error": {"type": "invalid_request_error", "param": "response.cancel"},
            }
        )
        await session.handle_upstream_event(
            {"type": "response.text.delta", "response_id": "resp_1", "delta": "旧回答"}
        )
        await session.handle_upstream_event(
            {"type": "response.done", "response": {"id": "resp_1", "status": "completed"}}
        )
        assert session.pending.turn_id == "turn_2"
        await session.handle_upstream_event(
            {"type": "response.text.delta", "response_id": "resp_2", "delta": "新回答"}
        )
        await session.handle_upstream_event(
            {"type": "response.done", "response": {"id": "resp_2", "status": "completed"}}
        )
        return service

    service = asyncio.run(scenario())

    assert service.persisted == [("第二个问题", "新回答")]


def test_upstream_reconnect_retries_with_backoff_and_resets_on_success(tmp_path: Path):
    async def scenario():
        browser = FakeBrowser()
        primary = FakeQwen()
        attempts = {"count": 0}

        def factory():
            attempts["count"] += 1
            client = FakeQwen(fail_open=attempts["count"] < 2)
            return client

        settings = replace(
            AppSettings.for_workspace(tmp_path),
            realtime_reconnect_max_attempts=3,
            realtime_reconnect_base_delay_ms=1,
        )
        session = VisitorRealtimeSession(
            browser,
            "visitor_a",
            "sess_1",
            settings,
            FakeConversationService(),
            primary,
            qwen_client_factory=factory,
        )
        await session.open()
        recovered = await session._try_reconnect(primary)
        return recovered, attempts["count"], session._reconnect_failures, session.upstream_available

    recovered, attempt_count, failures, available = asyncio.run(scenario())

    assert recovered is True
    assert attempt_count == 2
    assert failures == 0
    assert available is True


def test_upstream_reconnect_exhausts_attempts(tmp_path: Path):
    async def scenario():
        browser = FakeBrowser()
        primary = FakeQwen()

        def factory():
            return FakeQwen(fail_open=True)

        settings = replace(
            AppSettings.for_workspace(tmp_path),
            realtime_reconnect_max_attempts=2,
            realtime_reconnect_base_delay_ms=1,
        )
        session = VisitorRealtimeSession(
            browser,
            "visitor_a",
            "sess_1",
            settings,
            FakeConversationService(),
            primary,
            qwen_client_factory=factory,
        )
        await session.open()
        recovered = await session._try_reconnect(primary)
        return recovered, session._reconnect_failures

    recovered, failures = asyncio.run(scenario())

    assert recovered is False
    assert failures == 2
