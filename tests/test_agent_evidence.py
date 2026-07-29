from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from lingjing_ai.agent.executor import AgentExecutor
from lingjing_ai.agent.models import ToolResult
from lingjing_ai.config.settings import AppSettings
from lingjing_ai.models.rag import SourceChunk
from lingjing_ai.services.conversation import ConversationMessage, build_conversation_context
from lingjing_ai.tools.amap_client import AmapClient
from lingjing_ai.tools.amap_tools import AmapRouteTool


class RaisingAnswerGenerator:
    def generate(self, *args, **kwargs):
        raise AssertionError("collect_evidence must not generate the final answer")


class EmptyVectorStore:
    def list_records(self):
        return []


class FakeRagTool:
    name = "rag_search"

    def __init__(self) -> None:
        self.pipeline = SimpleNamespace(
            answer_generator=RaisingAnswerGenerator(),
            vector_store=EmptyVectorStore(),
        )

    def run(self, question: str) -> ToolResult:
        source = SourceChunk(
            chunk_id="chunk_1",
            document_id="doc_1",
            document_name="灵山资料.md",
            content="灵山胜境以灵山大佛闻名。",
            score=0.91,
            metadata={"source_type": "knowledge"},
        )
        return ToolResult(status="ok", message="命中资料", sources=[source])


class CountingRouteTool:
    name = "amap_route"

    def __init__(self) -> None:
        self.calls = 0

    def run(self, question: str) -> ToolResult:
        self.calls += 1
        return ToolResult(status="error", message="不应调用")


def test_collect_evidence_returns_sources_without_generating_answer(tmp_path: Path):
    settings = replace(
        AppSettings.for_workspace(tmp_path),
        agent_fast_tool_path_enabled=False,
        agent_use_query_rewrite=False,
        agent_use_document_search=False,
        agent_use_map_tools=False,
        question_expansion_enabled=False,
    )
    executor = AgentExecutor(settings=settings, tools=[FakeRagTool()])

    evidence = executor.collect_evidence("灵山胜境有什么特色？")

    assert evidence.question == "灵山胜境有什么特色？"
    assert evidence.sources[0].document_name == "灵山资料.md"
    assert evidence.confidence == 0.91
    assert evidence.is_answered is True
    assert [trace.tool_name for trace in evidence.tool_trace] == ["rag_search"]


def test_route_question_with_missing_endpoint_clarifies_without_calling_amap(tmp_path: Path):
    settings = replace(
        AppSettings.for_workspace(tmp_path),
        agent_use_query_rewrite=False,
        agent_use_document_search=False,
        question_expansion_enabled=False,
    )
    route_tool = CountingRouteTool()
    executor = AgentExecutor(settings=settings, tools=[FakeRagTool(), route_tool])

    evidence = executor.collect_evidence("到灵山胜境怎么走？")

    assert evidence.needs_clarification is True
    assert "起点" in evidence.clarifying_question
    assert route_tool.calls == 0
    assert evidence.sources == []


def test_existing_history_internal_route_collects_one_successful_amap_source(tmp_path: Path):
    settings = replace(
        AppSettings.for_workspace(tmp_path),
        question_expansion_enabled=False,
        agent_use_query_rewrite=False,
        agent_use_document_search=False,
    )
    calls = []
    locations = {"五明桥": "120.102248,31.421749", "五智门": "120.101292,31.423055"}

    def fake_walking_route(origin: str, destination: str) -> dict:
        calls.append((origin, destination))
        return {
            "route": {
                "paths": [{
                    "distance": "210",
                    "duration": "180",
                    "steps": [{
                        "instruction": "沿景区步道步行至五智门",
                        "polyline": f"{origin};{destination}",
                    }],
                }]
            }
        }

    client = AmapClient(api_key="map-key")
    client.walking_route = fake_walking_route
    route_tool = AmapRouteTool(settings, client=client, location_resolver=locations.get)
    executor = AgentExecutor(settings=settings, tools=[FakeRagTool(), route_tool])
    context = build_conversation_context(
        "从五明桥到五智门怎么走",
        [ConversationMessage("assistant", "建议先游览灵山大佛。")],
    )

    evidence = executor.collect_evidence("从五明桥到五智门怎么走", context)

    assert calls == [(locations["五明桥"], locations["五智门"])]
    assert evidence.needs_clarification is False
    assert [trace.tool_name for trace in evidence.tool_trace] == ["amap_route"]
    assert evidence.tool_trace[0].status == "ok"
    assert evidence.sources[0].metadata["route_summary"]["mode"] == "walking"


def test_lite_profile_skips_query_rewrite_and_document_search(tmp_path: Path):
    settings = replace(
        AppSettings.for_workspace(tmp_path),
        agent_fast_tool_path_enabled=False,
        agent_use_query_rewrite=True,
        agent_use_document_search=True,
        agent_use_map_tools=False,
        question_expansion_enabled=False,
    )
    executor = AgentExecutor(settings=settings, tools=[FakeRagTool()])

    evidence = executor.collect_evidence("灵山胜境有什么特色？", profile="lite")

    assert [trace.tool_name for trace in evidence.tool_trace] == ["rag_search"]


class SlowTool:
    def __init__(self, name: str, delay: float, content: str) -> None:
        self.name = name
        self.delay = delay
        self.content = content
        self.started_at: list[float] = []
        # AgentExecutor 要求至少一个工具挂着 pipeline 引用。
        self.pipeline = SimpleNamespace(
            answer_generator=RaisingAnswerGenerator(),
            vector_store=EmptyVectorStore(),
        )

    def run(self, question: str) -> ToolResult:
        import time

        self.started_at.append(time.perf_counter())
        time.sleep(self.delay)
        return ToolResult(
            status="ok",
            message=self.name,
            sources=[
                SourceChunk(
                    chunk_id=f"{self.name}_1",
                    document_id=self.name,
                    document_name=f"{self.name}.md",
                    content=self.content,
                    score=0.8,
                    metadata={"source_type": "knowledge"},
                )
            ],
        )


def test_collect_evidence_runs_independent_tools_in_parallel(tmp_path: Path):
    settings = replace(
        AppSettings.for_workspace(tmp_path),
        agent_fast_tool_path_enabled=False,
        agent_use_query_rewrite=False,
        agent_use_document_search=True,
        agent_use_map_tools=False,
        kg_enabled=False,
        question_expansion_enabled=False,
    )
    rag = SlowTool("rag_search", 0.05, "rag")
    document = SlowTool("document_search", 0.05, "doc")
    executor = AgentExecutor(settings=settings, tools=[rag, document])

    import time

    started = time.perf_counter()
    evidence = executor.collect_evidence("灵山胜境有什么特色？", profile="full")
    elapsed = time.perf_counter() - started

    assert {trace.tool_name for trace in evidence.tool_trace} == {"rag_search", "document_search"}
    assert elapsed < 0.09
    assert abs(rag.started_at[0] - document.started_at[0]) < 0.04
