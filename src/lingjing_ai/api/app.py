from dataclasses import dataclass, field
from pathlib import Path
import json
import math
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from lingjing_ai.api.analytics_routes import build_analytics_router
from lingjing_ai.api.attraction_routes import build_attraction_router
from lingjing_ai.api.feedback_routes import build_feedback_router
from lingjing_ai.api.food_routes import build_food_router
from lingjing_ai.api.realtime_routes import build_realtime_router
from lingjing_ai.agent.executor import AgentExecutor
from lingjing_ai.agent.langgraph_executor import LangGraphAgentExecutor
from lingjing_ai.agent.models import AgentAnswer, ToolTrace
from lingjing_ai.models.rag import RagAnswer, SourceChunk
from lingjing_ai.rag.llm_client import AliyunQwenClient
from lingjing_ai.rag.pipeline import RagPipeline
from lingjing_ai.realtime.conversation import RealtimeConversationService
from lingjing_ai.realtime.glossary import GlossaryProvider
from lingjing_ai.realtime.transcript import TranscriptNormalizer
from lingjing_ai.services.conversation import ConversationMessage, build_conversation_context
from lingjing_ai.services.conversation_store import (
    ConversationSessionRecord,
    ConversationStore,
    StoredChatMessage,
)
from lingjing_ai.services.attraction_store import AttractionStore
from lingjing_ai.services.analytics_snapshot import AnalyticsSnapshotStore
from lingjing_ai.services.feedback_store import FeedbackStore
from lingjing_ai.services.food_store import FoodStore
from lingjing_ai.services.question_expansion import QwenQuestionExpander
from lingjing_ai.tools.amap_tools import AmapPlaceSearchTool, AmapRouteTool, AmapWeatherTool
from lingjing_ai.tools.route_scope import ScenicNavigationScope
from lingjing_ai.tools.document_search_tool import DocumentSearchTool
from lingjing_ai.tools.kg_search_tool import KnowledgeGraphSearchTool
from lingjing_ai.tools.query_rewrite_tool import QueryRewriteTool
from lingjing_ai.tools.rag_search_tool import RagSearchTool
from lingjing_ai.tools.web_search_tool import WebSearchTool


class ConversationMessageRequest(BaseModel):
    role: str = Field(default="user")
    content: str = Field(default="")


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    history: list[ConversationMessageRequest] = Field(default_factory=list)
    session_id: str = ""
    visitor_id: str = ""
    persist_history: bool = True


class SourceResponse(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    content_preview: str
    score: float
    metadata: dict = Field(default_factory=dict)


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceResponse]
    confidence: float
    is_answered: bool
    trace_id: str
    needs_clarification: bool = False
    clarifying_question: str = ""
    session_id: str = ""
    session_title: str = ""


class ToolTraceResponse(BaseModel):
    tool_name: str
    tool_input: str
    status: str
    message: str
    source_count: int


class AgentChatResponse(ChatResponse):
    tool_trace: list[ToolTraceResponse]


class UploadDocumentResponse(BaseModel):
    document_id: str
    document_name: str
    saved_path: str
    indexed_chunks: int
    vector_store: str
    message: str


class DocumentRecordResponse(BaseModel):
    document_id: str
    document_name: str
    saved_path: str
    file_md5: str
    file_size: int
    indexed_chunks: int
    created_at: str
    updated_at: str


class DocumentListResponse(BaseModel):
    documents: list[DocumentRecordResponse]


class DocumentContentResponse(BaseModel):
    document_id: str
    document_name: str
    content: str


class AdminActionResponse(BaseModel):
    document_id: str
    message: str


class KnowledgeGraphStatusResponse(BaseModel):
    enabled: bool
    node_count: int
    relationship_count: int
    schema_version: str = "scenic_v1"
    message: str
    indexed_chunks: int = 0


class ToolQueryResponse(BaseModel):
    status: str
    message: str
    content: str
    data: dict


class MapConfigResponse(BaseModel):
    enabled: bool
    js_api_key: str
    security_js_code: str
    default_route_mode: str
    message: str


class VisitorSessionResponse(BaseModel):
    session_id: str
    visitor_id: str
    title: str
    recent_question: str
    created_at: str
    updated_at: str


class VisitorSessionListResponse(BaseModel):
    sessions: list[VisitorSessionResponse]


class VisitorMessageResponse(BaseModel):
    message_id: int
    session_id: str
    role: str
    content: str
    trace_id: str
    sources: list[dict] = Field(default_factory=list)
    tool_trace: list[dict] = Field(default_factory=list)
    created_at: str


class VisitorMessageListResponse(BaseModel):
    session_id: str
    messages: list[VisitorMessageResponse]


class VisitorSessionDeleteResponse(BaseModel):
    session_id: str
    message: str


@dataclass(frozen=True)
class RequestConversationState:
    context: Any
    session_id: str = ""
    session_title: str = ""
    visitor_id: str = ""


@dataclass
class StreamTurnState:
    answer_parts: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    tool_trace: list[dict] = field(default_factory=list)
    trace_id: str = ""


def create_app(
    pipeline: RagPipeline,
    seed_attractions: bool = True,
    seed_foods: bool = True,
) -> FastAPI:
    app = FastAPI(title="灵境智导 RAG API")
    frontend_dir = _project_root() / "frontend"
    visitor_dist_dir = frontend_dir / "dist"
    visitor_assets_dir = visitor_dist_dir / "assets"
    visitor_digital_human_dir = visitor_dist_dir / "digital-human"
    required_avatar_dirs = ("mao_pro", "chitose", "haruto")
    if not all(
        (visitor_digital_human_dir / "live2d" / avatar_id).is_dir()
        for avatar_id in required_avatar_dirs
    ):
        # A stale build may contain only some roles, so use complete public sources to avoid partial 404s.
        visitor_digital_human_dir = frontend_dir / "public" / "digital-human"
    static_dir = frontend_dir / "static"
    attraction_image_dir = pipeline.settings.data_dir / "attraction_images"
    database_url = pipeline.settings.database_url.strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for PostgreSQL storage")
    schema_prefix = pipeline.settings.database_schema_prefix
    attraction_store = AttractionStore(
        database_url,
        attraction_image_dir,
        seed_on_empty=seed_attractions,
        schema=f"{schema_prefix}attractions",
    )
    food_image_dir = pipeline.settings.data_dir / "food_images"
    food_store = FoodStore(
        database_url,
        food_image_dir,
        seed_on_empty=seed_foods,
        schema=f"{schema_prefix}foods",
    )
    feedback_store = FeedbackStore(database_url, schema=f"{schema_prefix}feedback")
    route_scope = _build_scenic_navigation_scope(pipeline, attraction_store)
    agent_executor = _build_agent_executor(pipeline, attraction_store, route_scope)
    question_expander = _build_question_expander(pipeline)
    conversation_store = ConversationStore(
        database_url,
        schema=f"{schema_prefix}conversations",
    )
    glossary_path = Path(pipeline.settings.asr_glossary_path)
    if not glossary_path.is_absolute():
        glossary_path = pipeline.settings.workspace_dir / glossary_path
    glossary_provider = GlossaryProvider(
        attraction_store,
        pipeline.document_manifest,
        glossary_path,
        ttl_seconds=pipeline.settings.asr_glossary_ttl_seconds,
    )
    transcript_normalizer = (
        TranscriptNormalizer(glossary_provider.snapshot)
        if pipeline.settings.asr_correction_enabled
        else None
    )
    realtime_conversation_service = RealtimeConversationService(
        pipeline.settings,
        conversation_store,
        agent_executor,
        question_expander,
        transcript_normalizer,
    )
    app.include_router(build_attraction_router(attraction_store))
    app.include_router(build_food_router(food_store))
    app.include_router(build_feedback_router(feedback_store))
    analytics_store = AnalyticsSnapshotStore(
        pipeline.settings.data_dir / "tourism_analytics_snapshot.json"
    )
    app.include_router(build_analytics_router(analytics_store))
    app.include_router(
        build_realtime_router(pipeline.settings, realtime_conversation_service)
    )
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.mount(
        "/media/attractions",
        StaticFiles(directory=attraction_image_dir),
        name="attraction_images",
    )
    app.mount(
        "/media/foods",
        StaticFiles(directory=food_image_dir),
        name="food_images",
    )
    if visitor_assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=visitor_assets_dir), name="visitor_assets")
    app.mount(
        "/digital-human",
        StaticFiles(directory=visitor_digital_human_dir),
        name="digital_human_assets",
    )

    @app.get("/pcm-capture-worklet.js", response_class=FileResponse)
    def visitor_pcm_capture_worklet() -> FileResponse:
        # Keep the old route because cached visitor builds may still request the pre-module Worklet URL.
        return FileResponse(
            visitor_digital_human_dir / "pcm-capture-worklet.js",
            media_type="application/javascript",
        )

    @app.get("/visitor")
    def visitor_page():
        dist_index = visitor_dist_dir / "index.html"
        if dist_index.is_file():
            return FileResponse(dist_index)
        return HTMLResponse(_visitor_build_hint_html())

    @app.get("/visitor/{page}")
    def visitor_subpage(page: str):
        if page not in {"guide", "explore", "map", "food", "feedback"}:
            raise HTTPException(status_code=404, detail="游客页面不存在。")
        dist_index = visitor_dist_dir / "index.html"
        if dist_index.is_file():
            return FileResponse(dist_index)
        return HTMLResponse(_visitor_build_hint_html())

    def admin_page_response(filename: str) -> FileResponse:
        # 管理页禁用 HTML 缓存，避免浏览器继续展示合并冲突前的旧导航结构。
        return FileResponse(frontend_dir / filename, headers={"Cache-Control": "no-store"})

    @app.get("/admin/documents", response_class=FileResponse)
    def admin_documents_page() -> FileResponse:
        return admin_page_response("admin_documents.html")

    @app.get("/admin/attractions", response_class=FileResponse)
    def admin_attractions_page() -> FileResponse:
        return admin_page_response("admin_attractions.html")

    @app.get("/admin/foods", response_class=FileResponse)
    def admin_foods_page() -> FileResponse:
        return admin_page_response("admin_foods.html")

    @app.get("/admin/feedback", response_class=FileResponse)
    def admin_feedback_page() -> FileResponse:
        return admin_page_response("admin_feedback.html")

    @app.get("/admin/analytics", response_class=FileResponse)
    def admin_analytics_page() -> FileResponse:
        return admin_page_response("admin_analytics.html")

    @app.post("/api/rag/chat", response_model=ChatResponse)
    def chat(request: ChatRequest) -> ChatResponse:
        state = _request_conversation_state(request, pipeline, question_expander, conversation_store)
        result = pipeline.ask(request.question, conversation_context=state.context)
        response = _to_chat_response(result, state)
        _persist_chat_turn(conversation_store, state, request.question, response)
        return response

    @app.post("/api/rag/chat/stream")
    def chat_stream(request: ChatRequest) -> StreamingResponse:
        def event_stream():
            try:
                state = _request_conversation_state(request, pipeline, question_expander, conversation_store)
                stream_state = StreamTurnState()
                for event in pipeline.ask_stream(request.question, conversation_context=state.context):
                    event = _augment_stream_event(event, state, stream_state)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                _persist_stream_turn(conversation_store, state, request.question, stream_state)
            except Exception:
                event = {"type": "error", "message": "流式问答服务暂时不可用，请稍后重试。"}
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.post("/api/agent/chat", response_model=AgentChatResponse)
    def agent_chat(request: ChatRequest) -> AgentChatResponse:
        state = _request_conversation_state(request, pipeline, question_expander, conversation_store)
        result = agent_executor.run(request.question, conversation_context=state.context)
        response = _to_agent_chat_response(result, state)
        _persist_chat_turn(conversation_store, state, request.question, response, response.tool_trace)
        return response

    @app.post("/api/agent/chat/stream")
    def agent_chat_stream(request: ChatRequest) -> StreamingResponse:
        def event_stream():
            try:
                state = _request_conversation_state(request, pipeline, question_expander, conversation_store)
                stream_state = StreamTurnState()
                for event in agent_executor.run_stream(request.question, conversation_context=state.context):
                    event = _augment_stream_event(event, state, stream_state)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                _persist_stream_turn(conversation_store, state, request.question, stream_state)
            except Exception:
                event = {"type": "error", "message": "智能体问答服务暂时不可用，请稍后重试。"}
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.get("/api/tools/weather", response_model=ToolQueryResponse)
    def query_weather(city: str) -> ToolQueryResponse:
        result = AmapWeatherTool(pipeline.settings).run(f"{city}天气")
        return _to_tool_query_response(result)

    @app.get("/api/tools/map/search", response_model=ToolQueryResponse)
    def query_map_search(keywords: str, city: str = "") -> ToolQueryResponse:
        query = f"{city} {keywords}".strip()
        result = AmapPlaceSearchTool(pipeline.settings).run(query)
        return _to_tool_query_response(result)

    @app.get("/api/tools/map/config", response_model=MapConfigResponse)
    def query_map_config() -> MapConfigResponse:
        js_api_key = pipeline.settings.map_js_api_key or ""
        security_js_code = pipeline.settings.map_js_security_code or ""
        enabled = bool(js_api_key and security_js_code)
        if not js_api_key:
            message = "未配置 MAP_JS_API，前端地图不可用。"
        elif not security_js_code:
            message = "未配置 MAP_JS_SECURITY_CODE，前端地图不可用。"
        else:
            message = "高德前端地图已配置"
        return MapConfigResponse(
            enabled=enabled,
            js_api_key=js_api_key,
            security_js_code=security_js_code,
            default_route_mode=pipeline.settings.amap_route_default_mode,
            message=message,
        )

    @app.get("/api/tools/map/route", response_model=ToolQueryResponse)
    def query_map_route(
        origin: str,
        destination: str,
        mode: str = "",
        origin_location: str = "",
        destination_location: str = "",
    ) -> ToolQueryResponse:
        result = AmapRouteTool(
            pipeline.settings,
            location_resolver=lambda name: _published_attraction_location(attraction_store, name),
            scope_validator=route_scope.validate,
        ).run(
            f"从{origin}到{destination}怎么走",
            mode=mode,
            origin_location=origin_location,
            destination_location=destination_location,
        )
        return _to_tool_query_response(result)

    @app.get("/api/visitor/sessions", response_model=VisitorSessionListResponse)
    def list_visitor_sessions(visitor_id: str) -> VisitorSessionListResponse:
        return VisitorSessionListResponse(
            sessions=[
                _to_visitor_session_response(session)
                for session in conversation_store.list_sessions(visitor_id)
            ]
        )

    @app.get("/api/visitor/sessions/{session_id}/messages", response_model=VisitorMessageListResponse)
    def list_visitor_messages(session_id: str, visitor_id: str) -> VisitorMessageListResponse:
        if conversation_store.get_session(session_id, visitor_id) is None:
            raise HTTPException(status_code=404, detail="会话不存在或无权访问。")
        return VisitorMessageListResponse(
            session_id=session_id,
            messages=[
                _to_visitor_message_response(message)
                for message in conversation_store.list_messages(session_id, visitor_id)
            ],
        )

    @app.delete("/api/visitor/sessions/{session_id}", response_model=VisitorSessionDeleteResponse)
    def delete_visitor_session(session_id: str, visitor_id: str) -> VisitorSessionDeleteResponse:
        if not conversation_store.delete_session(session_id, visitor_id):
            raise HTTPException(status_code=404, detail="会话不存在或无权删除。")
        return VisitorSessionDeleteResponse(session_id=session_id, message="会话已删除")

    @app.post("/api/rag/documents/upload", response_model=UploadDocumentResponse)
    async def upload_document(file: UploadFile = File(...)) -> UploadDocumentResponse:
        return await _ingest_upload(file, pipeline)

    @app.get("/api/admin/documents", response_model=DocumentListResponse)
    def list_admin_documents() -> DocumentListResponse:
        return DocumentListResponse(
            documents=[_to_document_record_response(record) for record in pipeline.list_documents()]
        )

    @app.get("/api/admin/documents/{document_id}/content", response_model=DocumentContentResponse)
    def get_admin_document_content(document_id: str) -> DocumentContentResponse:
        record = pipeline.document_manifest.get(document_id)
        content = pipeline.get_document_content(document_id)
        if record is None or content is None:
            raise HTTPException(status_code=404, detail="资料不存在或无法预览。")
        return DocumentContentResponse(
            document_id=record.document_id,
            document_name=record.document_name,
            content=content,
        )

    @app.post("/api/admin/documents/upload", response_model=UploadDocumentResponse)
    async def upload_admin_document(file: UploadFile = File(...)) -> UploadDocumentResponse:
        return await _ingest_upload(file, pipeline)

    @app.post("/api/admin/documents/{document_id}/reindex", response_model=DocumentRecordResponse)
    def reindex_admin_document(document_id: str) -> DocumentRecordResponse:
        record = pipeline.reindex_document(document_id)
        if record is None:
            raise HTTPException(status_code=404, detail="资料不存在，无法重新解析。")
        return _to_document_record_response(record)

    @app.delete("/api/admin/documents/{document_id}", response_model=AdminActionResponse)
    def delete_admin_document(document_id: str) -> AdminActionResponse:
        if not pipeline.delete_document(document_id):
            raise HTTPException(status_code=404, detail="资料不存在，无法删除。")
        return AdminActionResponse(document_id=document_id, message="资料已删除")

    @app.get("/api/admin/knowledge-graph/status", response_model=KnowledgeGraphStatusResponse)
    def knowledge_graph_status() -> KnowledgeGraphStatusResponse:
        return _to_knowledge_graph_status_response(pipeline.knowledge_graph.status())

    @app.post("/api/admin/knowledge-graph/rebuild", response_model=KnowledgeGraphStatusResponse)
    def rebuild_knowledge_graph() -> KnowledgeGraphStatusResponse:
        indexed_chunks = pipeline.rebuild_knowledge_graph_from_manifest()
        status = pipeline.knowledge_graph.status()
        status["indexed_chunks"] = indexed_chunks
        return _to_knowledge_graph_status_response(status)

    return app


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _visitor_build_hint_html() -> str:
    return """
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>灵境智导游客端</title>
    <style>
      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        font-family: "Microsoft YaHei", Arial, sans-serif;
        color: #202634;
        background: #fff;
      }
      #app {
        width: min(680px, calc(100% - 32px));
        border: 1px solid #e6eaf1;
        border-radius: 8px;
        padding: 28px;
        box-shadow: 0 18px 44px rgba(35, 42, 60, 0.08);
      }
      code {
        display: block;
        margin-top: 12px;
        padding: 12px;
        border-radius: 8px;
        background: #f7f8fb;
      }
    </style>
  </head>
  <body>
    <main id="app">
      <h1>Vue 游客端尚未构建</h1>
      <p>请在项目根目录执行前端依赖安装和构建，然后刷新本页。</p>
      <code>cd frontend<br />npm install<br />npm run build</code>
    </main>
  </body>
</html>
"""


def _build_agent_executor(
    pipeline: RagPipeline,
    attraction_store: AttractionStore | None = None,
    route_scope: ScenicNavigationScope | None = None,
) -> AgentExecutor:
    location_resolver = (
        (lambda name: _published_attraction_location(attraction_store, name))
        if attraction_store is not None
        else None
    )
    if route_scope is None and attraction_store is not None:
        route_scope = _build_scenic_navigation_scope(pipeline, attraction_store)
    tools = [
        QueryRewriteTool(),
        RagSearchTool(pipeline),
        KnowledgeGraphSearchTool(pipeline),
        DocumentSearchTool(pipeline),
        AmapWeatherTool(pipeline.settings),
        AmapRouteTool(
            pipeline.settings,
            location_resolver=location_resolver,
            scope_validator=route_scope.validate if route_scope is not None else None,
        ),
        AmapPlaceSearchTool(pipeline.settings),
        WebSearchTool(pipeline.settings),
    ]
    if pipeline.settings.agent_executor_mode == "legacy":
        return AgentExecutor(settings=pipeline.settings, tools=tools)
    if pipeline.settings.agent_executor_mode == "langgraph":
        return LangGraphAgentExecutor(settings=pipeline.settings, tools=tools)
    raise ValueError("AGENT_EXECUTOR_MODE 仅支持 legacy 或 langgraph。")


def _published_attraction_location(
    attraction_store: AttractionStore,
    name: str,
) -> str | None:
    attraction = attraction_store.get_published_attraction_by_name(name)
    if attraction is None:
        return None
    if not math.isfinite(attraction.longitude) or not math.isfinite(attraction.latitude):
        return None
    if attraction.longitude == 0 or attraction.latitude == 0:
        return None
    # The shared coordinate formatter keeps Agent and HTTP route requests on the same local truth.
    return f"{attraction.longitude},{attraction.latitude}"


def _build_scenic_navigation_scope(
    pipeline: RagPipeline,
    attraction_store: AttractionStore,
) -> ScenicNavigationScope:
    return ScenicNavigationScope(
        lambda: _published_attraction_locations(attraction_store),
        radius_km=pipeline.settings.amap_scenic_navigation_radius_km,
    )


def _published_attraction_locations(attraction_store: AttractionStore) -> list[str]:
    locations = []
    for attraction in attraction_store.list_attractions(public_only=True):
        if not math.isfinite(attraction.longitude) or not math.isfinite(attraction.latitude):
            continue
        if attraction.longitude == 0 or attraction.latitude == 0:
            continue
        # Refresh anchors per request so publication and coordinate edits immediately affect the safety boundary.
        locations.append(f"{attraction.longitude},{attraction.latitude}")
    return locations


def _build_question_expander(pipeline: RagPipeline) -> QwenQuestionExpander | None:
    if not pipeline.settings.question_expansion_enabled or not pipeline.settings.llm_api_key:
        return None
    model_name = pipeline.settings.question_expansion_model or "qwen3.7-plus"
    client = AliyunQwenClient(
        api_key=pipeline.settings.llm_api_key,
        model=model_name,
        base_url=pipeline.settings.llm_base_url,
        timeout_seconds=pipeline.settings.llm_timeout_seconds,
    )
    return QwenQuestionExpander(client, model_name=model_name)


async def _ingest_upload(file: UploadFile, pipeline: RagPipeline) -> UploadDocumentResponse:
    document_name = Path(file.filename or "").name
    if not document_name:
        raise HTTPException(status_code=400, detail="资料文件名不能为空。")

    suffix = Path(document_name).suffix.lower()
    if suffix not in pipeline.settings.allowed_upload_extensions:
        allowed = "、".join(pipeline.settings.allowed_upload_extensions)
        raise HTTPException(status_code=400, detail=f"仅支持 {allowed} 格式的资料文件。")

    content = await file.read()
    if len(content) > pipeline.settings.max_upload_bytes:
        raise HTTPException(status_code=400, detail="资料文件大小超过限制。")
    if not content:
        raise HTTPException(status_code=400, detail="资料文件内容不能为空。")

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="资料文件必须使用 UTF-8 编码。") from exc
    if not text.strip():
        raise HTTPException(status_code=400, detail="资料文件内容不能为空。")

    before_count = pipeline.vector_store.count()
    document = pipeline.ingest_uploaded_text(document_name, text)
    after_count = pipeline.vector_store.count()
    return UploadDocumentResponse(
        document_id=document.id,
        document_name=document.name,
        saved_path=document.path,
        indexed_chunks=max(0, after_count - before_count),
        vector_store=str(pipeline.vector_store.path),
        message="资料已导入知识库",
    )


def _to_chat_response(result: RagAnswer, state: RequestConversationState | None = None) -> ChatResponse:
    return ChatResponse(
        answer=result.answer,
        sources=[_to_source_response(source) for source in result.sources],
        confidence=result.confidence,
        is_answered=result.is_answered,
        trace_id=result.trace_id,
        needs_clarification=result.needs_clarification,
        clarifying_question=result.clarifying_question,
        session_id=state.session_id if state else "",
        session_title=state.session_title if state else "",
    )


def _to_agent_chat_response(result: AgentAnswer, state: RequestConversationState | None = None) -> AgentChatResponse:
    return AgentChatResponse(
        answer=result.answer,
        sources=[_to_source_response(source) for source in result.sources],
        confidence=result.confidence,
        is_answered=result.is_answered,
        trace_id=result.trace_id,
        needs_clarification=result.needs_clarification,
        clarifying_question=result.clarifying_question,
        session_id=state.session_id if state else "",
        session_title=state.session_title if state else "",
        tool_trace=[_to_tool_trace_response(trace) for trace in result.tool_trace],
    )


def _request_conversation_state(
    request: ChatRequest,
    pipeline: RagPipeline,
    question_expander: QwenQuestionExpander | None,
    conversation_store: ConversationStore,
) -> RequestConversationState:
    session = _resolve_session(request, conversation_store)
    history = _history_for_request(request, conversation_store, session)
    context = _conversation_context_from_messages(request, pipeline, question_expander, history)
    return RequestConversationState(
        context=context,
        session_id=session.session_id if session else "",
        session_title=session.title if session else "",
        visitor_id=session.visitor_id if session else "",
    )


def _resolve_session(
    request: ChatRequest,
    conversation_store: ConversationStore,
) -> ConversationSessionRecord | None:
    visitor_id = request.visitor_id.strip()
    if not request.persist_history or not visitor_id:
        return None
    session_id = request.session_id.strip()
    if session_id:
        session = conversation_store.get_session(session_id, visitor_id)
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在或无权访问。")
        return session
    return conversation_store.create_session(visitor_id, request.question)


def _history_for_request(
    request: ChatRequest,
    conversation_store: ConversationStore,
    session: ConversationSessionRecord | None,
) -> list[ConversationMessage]:
    if session is not None:
        stored_messages = conversation_store.recent_messages(session.session_id, session.visitor_id, limit=12)
        if stored_messages:
            return [
                ConversationMessage(role=message.role, content=message.content)
                for message in stored_messages
            ]
    return [
        ConversationMessage(role=message.role, content=message.content)
        for message in request.history
    ]


def _conversation_context(
    request: ChatRequest,
    pipeline: RagPipeline,
    question_expander: QwenQuestionExpander | None,
):
    history = [ConversationMessage(role=message.role, content=message.content) for message in request.history]
    return _conversation_context_from_messages(request, pipeline, question_expander, history)


def _conversation_context_from_messages(
    request: ChatRequest,
    pipeline: RagPipeline,
    question_expander: QwenQuestionExpander | None,
    history: list[ConversationMessage],
):
    return build_conversation_context(
        request.question,
        history,
        question_expander=question_expander,
        max_expansion_candidates=pipeline.settings.question_expansion_max_candidates,
        expansion_top_n=pipeline.settings.question_expansion_top_n,
        question_expansion_auto_skip=pipeline.settings.question_expansion_auto_skip,
    )


def _persist_chat_turn(
    conversation_store: ConversationStore,
    state: RequestConversationState,
    question: str,
    response: ChatResponse,
    tool_trace: list[ToolTraceResponse] | None = None,
) -> None:
    if not state.session_id or not state.visitor_id:
        return
    conversation_store.append_message(state.session_id, state.visitor_id, "user", question)
    conversation_store.append_message(
        state.session_id,
        state.visitor_id,
        "assistant",
        response.answer,
        trace_id=response.trace_id,
        sources=[_model_to_dict(source) for source in response.sources],
        tool_trace=[_model_to_dict(trace) for trace in (tool_trace or [])],
    )


def _persist_stream_turn(
    conversation_store: ConversationStore,
    state: RequestConversationState,
    question: str,
    stream_state: StreamTurnState,
) -> None:
    if not state.session_id or not state.visitor_id:
        return
    answer = "".join(stream_state.answer_parts).strip()
    if not answer:
        return
    conversation_store.append_message(state.session_id, state.visitor_id, "user", question)
    conversation_store.append_message(
        state.session_id,
        state.visitor_id,
        "assistant",
        answer,
        trace_id=stream_state.trace_id,
        sources=stream_state.sources,
        tool_trace=stream_state.tool_trace,
    )


def _augment_stream_event(
    event: dict[str, Any],
    state: RequestConversationState,
    stream_state: StreamTurnState,
) -> dict[str, Any]:
    event_type = event.get("type")
    if event_type == "meta":
        event = {
            **event,
            "session_id": state.session_id,
            "session_title": state.session_title,
        }
        stream_state.trace_id = str(event.get("trace_id", ""))
        stream_state.sources = list(event.get("sources") or [])
        stream_state.tool_trace = list(event.get("tool_trace") or [])
        return event
    if event_type == "token":
        stream_state.answer_parts.append(str(event.get("content", "")))
        return event
    if event_type == "done":
        event = {
            **event,
            "session_id": state.session_id,
            "session_title": state.session_title,
        }
        stream_state.trace_id = stream_state.trace_id or str(event.get("trace_id", ""))
    return event


def _to_source_response(source: SourceChunk) -> SourceResponse:
    return SourceResponse(
        chunk_id=source.chunk_id,
        document_id=source.document_id,
        document_name=source.document_name,
        content_preview=source.content[:120],
        score=source.score,
        metadata=source.metadata,
    )


def _to_tool_trace_response(trace: ToolTrace) -> ToolTraceResponse:
    return ToolTraceResponse(
        tool_name=trace.tool_name,
        tool_input=trace.tool_input,
        status=trace.status,
        message=trace.message,
        source_count=trace.source_count,
    )


def _to_visitor_session_response(session: ConversationSessionRecord) -> VisitorSessionResponse:
    return VisitorSessionResponse(
        session_id=session.session_id,
        visitor_id=session.visitor_id,
        title=session.title,
        recent_question=session.recent_question,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _to_visitor_message_response(message: StoredChatMessage) -> VisitorMessageResponse:
    return VisitorMessageResponse(
        message_id=message.message_id,
        session_id=message.session_id,
        role=message.role,
        content=message.content,
        trace_id=message.trace_id,
        sources=message.sources,
        tool_trace=message.tool_trace,
        created_at=message.created_at,
    )


def _model_to_dict(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    return dict(model)


def _to_tool_query_response(result) -> ToolQueryResponse:
    return ToolQueryResponse(
        status=result.status,
        message=result.message,
        content=result.sources[0].content if result.sources else "",
        data=result.data,
    )


def _to_knowledge_graph_status_response(status: dict) -> KnowledgeGraphStatusResponse:
    return KnowledgeGraphStatusResponse(
        enabled=bool(status.get("enabled")),
        node_count=int(status.get("node_count", 0)),
        relationship_count=int(status.get("relationship_count", 0)),
        schema_version=str(status.get("schema_version", "scenic_v1")),
        message=str(status.get("message", "")),
        indexed_chunks=int(status.get("indexed_chunks", 0)),
    )


def _to_document_record_response(record) -> DocumentRecordResponse:
    return DocumentRecordResponse(
        document_id=record.document_id,
        document_name=record.document_name,
        saved_path=record.saved_path,
        file_md5=record.file_md5,
        file_size=record.file_size,
        indexed_chunks=record.indexed_chunks,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
