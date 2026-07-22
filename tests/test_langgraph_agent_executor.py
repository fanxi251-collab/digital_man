from dataclasses import replace
from pathlib import Path
import asyncio

import httpx
import pytest

pytestmark = pytest.mark.usefixtures("postgres_test_context")

from lingjing_ai.agent.executor import AgentExecutor
from lingjing_ai.agent.models import ToolResult
from lingjing_ai.api.app import _build_agent_executor, create_app
from lingjing_ai.config.settings import AppSettings
from lingjing_ai.models.rag import SourceChunk
from lingjing_ai.rag.embeddings import HashingEmbeddingProvider
from lingjing_ai.rag.generator import ExtractiveAnswerGenerator
from lingjing_ai.rag.pipeline import RagPipeline
from lingjing_ai.storage.vector_store import JsonVectorStore
from lingjing_ai.tools.document_search_tool import DocumentSearchTool
from lingjing_ai.tools.query_rewrite_tool import QueryRewriteTool
from lingjing_ai.tools.rag_search_tool import RagSearchTool


def build_pipeline(tmp_path: Path, settings: AppSettings | None = None) -> RagPipeline:
    active_settings = settings or AppSettings.for_workspace(tmp_path)
    pipeline = RagPipeline(
        settings=active_settings,
        embedding_provider=HashingEmbeddingProvider(dimensions=64),
        vector_store=JsonVectorStore(tmp_path / "vectors.json"),
        answer_generator=ExtractiveAnswerGenerator(),
    )
    pipeline.ingest_uploaded_text(
        "灵境山资料.md",
        "灵境山适合老人轻松游览，古栈道沿途设有休息点。",
    )
    return pipeline


def test_build_agent_executor_uses_legacy_mode_by_default(tmp_path: Path):
    pipeline = build_pipeline(tmp_path)

    executor = _build_agent_executor(pipeline)

    assert isinstance(executor, AgentExecutor)
    assert executor.__class__ is AgentExecutor


def test_build_agent_executor_uses_langgraph_mode_when_configured(tmp_path: Path):
    settings = replace(AppSettings.for_workspace(tmp_path), agent_executor_mode="langgraph")
    pipeline = build_pipeline(tmp_path, settings)

    executor = _build_agent_executor(pipeline)

    assert executor.__class__.__name__ == "LangGraphAgentExecutor"


def test_langgraph_mode_reports_clear_error_when_dependency_missing(tmp_path: Path, monkeypatch):
    from lingjing_ai.agent import langgraph_executor

    monkeypatch.setattr(langgraph_executor, "StateGraph", None)
    settings = replace(AppSettings.for_workspace(tmp_path), agent_executor_mode="langgraph")
    pipeline = build_pipeline(tmp_path, settings)

    with pytest.raises(RuntimeError, match="LangGraph 未安装"):
        _build_agent_executor(pipeline)


class EmptyRagSearchTool:
    name = "rag_search"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def run(self, query: str) -> ToolResult:
        self.calls.append(query)
        return ToolResult(status="empty", message="empty", sources=[])


class EmptyDocumentSearchTool:
    name = "document_search"

    def run(self, query: str) -> ToolResult:
        return ToolResult(status="empty", message="empty", sources=[])


def test_langgraph_reflection_retries_empty_evidence_until_loop_limit(tmp_path: Path):
    from lingjing_ai.agent.langgraph_executor import LangGraphAgentExecutor

    settings = replace(
        AppSettings.for_workspace(tmp_path),
        agent_executor_mode="langgraph",
        agent_use_query_rewrite=False,
        agent_use_document_search=True,
        langgraph_max_loops=1,
        langgraph_reflection_enabled=True,
    )
    pipeline = build_pipeline(tmp_path, settings)
    rag_tool = EmptyRagSearchTool()
    executor = LangGraphAgentExecutor(
        settings=settings,
        tools=[
            rag_tool,
            EmptyDocumentSearchTool(),
            RagSearchTool(pipeline),
            DocumentSearchTool(pipeline),
        ],
    )
    executor.tools["rag_search"] = rag_tool
    executor.tools["document_search"] = EmptyDocumentSearchTool()

    result = executor.run("完全没有资料的问题")

    assert result.is_answered is False
    assert len([trace for trace in result.tool_trace if trace.tool_name == "rag_search"]) == 2
    assert rag_tool.calls == ["完全没有资料的问题", "完全没有资料的问题 详细资料"]


def test_langgraph_executor_keeps_agent_answer_contract(tmp_path: Path):
    from lingjing_ai.agent.langgraph_executor import LangGraphAgentExecutor

    settings = replace(AppSettings.for_workspace(tmp_path), agent_executor_mode="langgraph")
    pipeline = build_pipeline(tmp_path, settings)
    executor = LangGraphAgentExecutor(
        settings=settings,
        tools=[
            QueryRewriteTool(),
            RagSearchTool(pipeline),
            DocumentSearchTool(pipeline),
        ],
    )

    result = executor.run("灵境山适合老人游玩吗？")

    assert result.is_answered is True
    assert "### 简要回答" in result.answer
    assert result.sources[0].document_name == "灵境山资料.md"
    assert [trace.tool_name for trace in result.tool_trace][:2] == ["query_rewrite", "rag_search"]


def test_langgraph_agent_chat_api_keeps_response_shape(tmp_path: Path):
    settings = replace(AppSettings.for_workspace(tmp_path), agent_executor_mode="langgraph")
    app = create_app(build_pipeline(tmp_path, settings))

    async def post_chat() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/api/agent/chat", json={"question": "灵境山适合老人游玩吗？"})

    response = asyncio.run(post_chat())
    body = response.json()

    assert response.status_code == 200
    assert body["is_answered"] is True
    assert "tool_trace" in body
    assert body["sources"][0]["document_name"] == "灵境山资料.md"
    assert "### 简要回答" in body["answer"]
