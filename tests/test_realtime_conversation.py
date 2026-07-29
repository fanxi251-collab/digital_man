from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.usefixtures("postgres_test_context")

from lingjing_ai.agent.executor import AgentExecutor
from lingjing_ai.agent.models import AgentEvidence, ToolTrace
from lingjing_ai.config.settings import AppSettings
from lingjing_ai.models.rag import SourceChunk
from lingjing_ai.realtime.conversation import RealtimeConversationService
from lingjing_ai.services.conversation_store import ConversationStore
from lingjing_ai.tools.amap_client import AmapClient
from lingjing_ai.tools.amap_tools import AmapRouteTool
from lingjing_ai.tools.route_scope import ScenicNavigationScope


class FakeAgentExecutor:
    def __init__(self) -> None:
        self.contexts = []

    def collect_evidence(self, question, conversation_context=None, profile="full"):
        self.contexts.append((conversation_context, profile))
        return AgentEvidence(
            question=conversation_context.standalone_question,
            sources=[
                SourceChunk(
                    chunk_id="chunk_1",
                    document_id="doc_1",
                    document_name="灵山资料.md",
                    content="灵山胜境开放时间以景区当日公告为准。",
                    score=0.88,
                    metadata={"section_path": "游览信息"},
                )
            ],
            confidence=0.88,
            is_answered=True,
            trace_id="trace_1",
            tool_trace=[ToolTrace("rag_search", question, "ok", "命中资料", 1)],
        )


class PipelineBackedNoopTool:
    name = "rag_search"
    pipeline = SimpleNamespace(answer_generator=object())

    def run(self, question):
        raise AssertionError(f"路线快速路径不应调用RAG：{question}")


def build_service(tmp_path: Path, pg_dsn: str, conversations_schema: str):
    settings = replace(
        AppSettings.for_workspace(tmp_path),
        question_expansion_enabled=False,
    )
    store = ConversationStore(pg_dsn, schema=conversations_schema)
    agent = FakeAgentExecutor()
    return RealtimeConversationService(settings, store, agent), store, agent


def test_prepare_turn_creates_session_and_formats_temporary_evidence(
    tmp_path: Path, pg_dsn: str, conversations_schema: str
):
    service, store, _ = build_service(tmp_path, pg_dsn, conversations_schema)

    prepared = service.prepare_turn("灵山胜境几点开放？", "visitor_a", "")

    assert prepared.session.session_id.startswith("sess_")
    assert prepared.evidence.question == "灵山胜境几点开放？"
    assert "临时证据" in prepared.evidence_prompt
    assert "灵山资料.md" in prepared.evidence_prompt
    assert store.list_messages(prepared.session.session_id, "visitor_a") == []


def test_prepare_turn_uses_lite_profile_by_default(tmp_path: Path, pg_dsn: str, conversations_schema: str):
    service, _, agent = build_service(tmp_path, pg_dsn, conversations_schema)

    service.prepare_turn("灵山胜境几点开放？", "visitor_a", "")

    assert agent.contexts[-1][1] == "lite"


def test_prepare_turn_writes_mode_specific_answer_contract_into_evidence_prompt(tmp_path: Path, pg_dsn: str, conversations_schema: str):
    service, _, _ = build_service(tmp_path, pg_dsn, conversations_schema)

    regular = service.prepare_turn("灵山胜境有什么特色？", "visitor_a", "", mode="text")
    avatar = service.prepare_turn(
        "灵山胜境有什么特色？",
        "visitor_a",
        regular.session.session_id,
        mode="avatar",
    )

    assert regular.answer_contract.profile == "text_detailed"
    assert "300—600字" in regular.evidence_prompt
    assert avatar.answer_contract.profile == "avatar_summary"
    assert "3—6句" in avatar.evidence_prompt


def test_avatar_style_is_temporary_and_does_not_change_persisted_history(tmp_path: Path, pg_dsn: str, conversations_schema: str):
    service, store, _ = build_service(tmp_path, pg_dsn, conversations_schema)

    prepared = service.prepare_turn(
        "灵山胜境怎么玩？",
        "visitor_a",
        "",
        mode="avatar",
        avatar_style="使用活泼易懂的短句，但不得省略路线事实。",
    )
    service.persist_completed(prepared, "建议先参观灵山大佛。")

    assert "角色表达：使用活泼易懂的短句" in prepared.evidence_prompt
    messages = store.list_messages(prepared.session.session_id, "visitor_a")
    assert [message.content for message in messages] == [
        "灵山胜境怎么玩？",
        "建议先参观灵山大佛。",
    ]
    assert all("角色表达" not in message.content for message in messages)


def test_prepare_turn_uses_same_session_history_across_modes(tmp_path: Path, pg_dsn: str, conversations_schema: str):
    service, store, agent = build_service(tmp_path, pg_dsn, conversations_schema)
    first = service.prepare_turn("灵山胜境有什么特色？", "visitor_a", "")
    service.persist_completed(first, "灵山胜境以灵山大佛闻名。")

    second = service.prepare_turn("那开放时间呢？", "visitor_a", first.session.session_id)

    assert second.session.session_id == first.session.session_id
    assert "灵山胜境" in second.evidence.question
    assert agent.contexts[-1][0].history[-1].role == "assistant"
    assert [message["role"] for message in service.upstream_history(first.session.session_id, "visitor_a")] == [
        "user",
        "assistant",
    ]


def test_prepare_turn_preserves_explicit_internal_route_in_existing_session(tmp_path: Path, pg_dsn: str, conversations_schema: str):
    service, _, agent = build_service(tmp_path, pg_dsn, conversations_schema)
    first = service.prepare_turn("灵山胜境适合老人的游玩路线", "visitor_a", "")
    service.persist_completed(first, "建议先游览灵山大佛。")

    route = service.prepare_turn(
        "从五明桥到五智门怎么走",
        "visitor_a",
        first.session.session_id,
    )

    assert route.evidence.question == "从五明桥到五智门怎么走"
    assert route.evidence.needs_clarification is False
    assert agent.contexts[-1][0].standalone_question == "从五明桥到五智门怎么走"


def test_avatar_turn_routes_cleaned_internal_attraction_names_through_amap(tmp_path: Path, pg_dsn: str, conversations_schema: str):
    settings = replace(
        AppSettings.for_workspace(tmp_path),
        question_expansion_enabled=False,
        agent_use_query_rewrite=False,
        agent_use_document_search=False,
    )
    locations = {
        "灵山大佛": "120.096477,31.430194",
        "九龙灌浴": "120.099984,31.424601",
    }
    requested = []

    def fake_walking_route(origin: str, destination: str) -> dict:
        requested.append((origin, destination))
        return {
            "route": {
                "paths": [{
                    "distance": "900",
                    "duration": "600",
                    "steps": [{"instruction": "沿景区步道前行", "polyline": f"{origin};{destination}"}],
                }]
            }
        }

    client = AmapClient(api_key="map-key")
    client.geocode = lambda address, city="": (_ for _ in ()).throw(
        AssertionError(f"本地景点不应调用地理编码：{address}")
    )
    client.walking_route = fake_walking_route
    scope = ScenicNavigationScope(lambda: locations.values(), radius_km=10.0)
    route_tool = AmapRouteTool(
        settings,
        client=client,
        location_resolver=locations.get,
        scope_validator=scope.validate,
    )
    agent = AgentExecutor(settings=settings, tools=[PipelineBackedNoopTool(), route_tool])
    store = ConversationStore(pg_dsn, schema=conversations_schema)
    service = RealtimeConversationService(settings, store, agent)

    prepared = service.prepare_turn(
        "从灵山大佛到九龙灌浴的步行路线",
        "visitor_a",
        "",
        mode="avatar",
    )

    assert requested == [(locations["灵山大佛"], locations["九龙灌浴"])]
    assert prepared.evidence.tool_trace[0].tool_name == "amap_route"
    assert prepared.evidence.tool_trace[0].status == "ok"
    summary = prepared.evidence.sources[0].metadata["route_summary"]
    assert summary["origin"] == "灵山大佛"
    assert summary["destination"] == "九龙灌浴"
    assert summary["mode"] == "walking"


def test_avatar_turn_rejects_out_of_scope_route_without_direction_or_sources(tmp_path: Path, pg_dsn: str, conversations_schema: str):
    settings = replace(
        AppSettings.for_workspace(tmp_path),
        question_expansion_enabled=False,
        agent_use_query_rewrite=False,
        agent_use_document_search=False,
    )
    anchors = {"灵山大佛": "120.096477,31.430194"}
    direction_calls = []
    client = AmapClient(api_key="map-key")
    client.geocode = lambda address, city="": {"geocodes": [{"location": "120.305000,31.590000"}]}
    client.driving_route = lambda *args: direction_calls.append(args)
    scope = ScenicNavigationScope(lambda: anchors.values(), radius_km=10.0)
    route_tool = AmapRouteTool(
        settings,
        client=client,
        location_resolver=anchors.get,
        scope_validator=scope.validate,
    )
    agent = AgentExecutor(settings=settings, tools=[PipelineBackedNoopTool(), route_tool])
    service = RealtimeConversationService(
        settings,
        ConversationStore(pg_dsn, schema=conversations_schema),
        agent,
    )

    prepared = service.prepare_turn(
        "从灵山大佛到无锡站驾车怎么走",
        "visitor_a",
        "",
        mode="avatar",
    )

    assert direction_calls == []
    assert prepared.evidence.sources == []
    assert prepared.evidence.tool_trace[0].status == "error"
    assert "10公里" in prepared.evidence.tool_trace[0].message


def test_completed_turn_is_persisted_once_and_wrong_visitor_is_rejected(tmp_path: Path, pg_dsn: str, conversations_schema: str):
    service, store, _ = build_service(tmp_path, pg_dsn, conversations_schema)
    prepared = service.prepare_turn("灵山胜境几点开放？", "visitor_a", "")

    service.persist_completed(prepared, "开放时间以景区公告为准。", "turn_1")
    service.persist_completed(prepared, "这条重复回答不应写入。", "turn_1")

    messages = store.list_messages(prepared.session.session_id, "visitor_a")
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[-1].sources[0]["document_name"] == "灵山资料.md"
    with pytest.raises(PermissionError):
        service.prepare_turn("继续问", "visitor_b", prepared.session.session_id)
