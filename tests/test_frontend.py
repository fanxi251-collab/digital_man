import asyncio
import json
from pathlib import Path

import httpx

from lingjing_ai.api.app import create_app
from lingjing_ai.config.settings import AppSettings
from lingjing_ai.rag.embeddings import HashingEmbeddingProvider
from lingjing_ai.rag.generator import ExtractiveAnswerGenerator
from lingjing_ai.rag.pipeline import RagPipeline
from lingjing_ai.storage.vector_store import JsonVectorStore


def build_pipeline(tmp_path: Path) -> RagPipeline:
    settings = AppSettings.for_workspace(tmp_path)
    return RagPipeline(
        settings=settings,
        embedding_provider=HashingEmbeddingProvider(dimensions=64),
        vector_store=JsonVectorStore(tmp_path / "vectors.json"),
        answer_generator=ExtractiveAnswerGenerator(),
    )


def request_path(app, path: str) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(path)

    return asyncio.run(send())


def test_visitor_page_is_served_by_fastapi(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    response = request_path(app, "/visitor")

    assert response.status_code == 200
    assert 'id="app"' in response.text
    assert "Vue 游客端尚未构建" in response.text or "/assets/" in response.text


def test_current_visitor_brand_uses_lingjing_zhidao():
    sources = (
        Path("frontend/src/App.vue").read_text(encoding="utf-8"),
        Path("frontend/src/components/ChatMain.vue").read_text(encoding="utf-8"),
        Path(
            "frontend/src/features/scenic-intro/components/ScenicIntro.vue"
        ).read_text(encoding="utf-8"),
        Path("frontend/index.html").read_text(encoding="utf-8"),
        Path("frontend/visitor.html").read_text(encoding="utf-8"),
    )

    for source in sources:
        assert "灵境智导" in source
        assert "LingJing AI" not in source
        assert "LINGJING AI" not in source

    chat_source = sources[1]
    assert "给灵境智导发送消息，例如：给我推荐灵山胜境的游玩路线" in chat_source


def test_brand_rename_preserves_internal_identifiers_and_updates_api_title():
    app_source = Path("src/lingjing_ai/api/app.py").read_text(encoding="utf-8")
    package_source = Path("pyproject.toml").read_text(encoding="utf-8")

    assert 'title="灵境智导 RAG API"' in app_source
    assert 'name = "lingjing-ai"' in package_source
    assert 'const VISITOR_STORAGE_KEY = "lingjing_visitor_id"' in Path(
        "frontend/src/lib/visitorIdentity.js"
    ).read_text(encoding="utf-8")
    assert '"lingjing_current_session_id"' in Path(
        "frontend/src/composables/useSessions.js"
    ).read_text(encoding="utf-8")
    assert '"lingjing_digital_human_avatar"' in Path(
        "frontend/src/features/digital-human/lib/live2dCharacters.js"
    ).read_text(encoding="utf-8")
    assert '"lingjing.guide.intro.seen.v1"' in Path(
        "frontend/src/features/scenic-intro/lib/introPolicy.js"
    ).read_text(encoding="utf-8")


def test_vue_source_contains_required_visitor_layout_and_api_calls():
    app_source = Path("frontend/src/views/GuideView.vue").read_text(encoding="utf-8")
    chat_source = Path("frontend/src/components/ChatMain.vue").read_text(encoding="utf-8")
    session_source = Path("frontend/src/components/SessionSidebar.vue").read_text(encoding="utf-8")
    chat_composable = Path("frontend/src/composables/useRealtimeChat.js").read_text(encoding="utf-8")
    transcript_confirmation_source = Path(
        "frontend/src/features/digital-human/components/TranscriptConfirmation.vue"
    ).read_text(encoding="utf-8")
    session_composable = Path("frontend/src/composables/useSessions.js").read_text(encoding="utf-8")
    styles = (
        Path("frontend/src/styles.css").read_text(encoding="utf-8")
        + Path("frontend/src/guide.css").read_text(encoding="utf-8")
    )

    assert "visitor-layout" in app_source
    assert "chat-main" in chat_source
    assert "session-sidebar" in session_source
    assert "history-drawer" in app_source
    assert "给灵境智导发送消息" in chat_source
    assert "常规模式" in chat_source
    assert "数字人模式" in chat_source
    assert "text.submit" in chat_composable
    assert "audio.start" in chat_composable
    assert "response.cancel" in chat_composable
    assert "user.transcript.confirmation_required" in chat_composable
    assert "transcript.confirm" in chat_composable
    assert "转写结果需要确认" in transcript_confirmation_source
    assert "buildRealtimeUrl" in chat_composable
    assert "retryQuestion" in chat_composable
    assert '@retry="emit(\'ask\', $event)"' in chat_source
    assert 'mode.value = nextMode' not in chat_source
    assert 'event.type === "assistant.text.done"' in chat_composable
    assert 'event.turn_id !== activeTurnId.value' in chat_composable
    assert '"/api/visitor/sessions?visitor_id="' in session_composable
    assert "`/api/visitor/sessions/${currentSessionId.value}?" in session_composable
    assert ".history-drawer" in styles
    assert ".composer-card" in styles


def test_digital_human_frontend_uses_local_pcm_and_replaceable_stage():
    feature_root = Path("frontend/src/features/digital-human")
    stage_source = (feature_root / "components/DigitalHumanStage.vue").read_text(
        encoding="utf-8"
    )
    audio_source = (feature_root / "composables/usePcmAudio.js").read_text(
        encoding="utf-8"
    )
    chat_source = Path("frontend/src/composables/useRealtimeChat.js").read_text(encoding="utf-8")
    guide_source = Path("frontend/src/views/GuideView.vue").read_text(encoding="utf-8")
    voice_controls_source = (feature_root / "components/DigitalHumanVoiceControls.vue").read_text(
        encoding="utf-8"
    )
    worklet_source = Path(
        "frontend/public/digital-human/pcm-capture-worklet.js"
    ).read_text(encoding="utf-8")

    assert "audioLevel" in stage_source
    assert "speaking" in stage_source
    assert "AudioWorkletNode" in audio_source
    assert "sampleRate: 24000" in audio_source
    assert "preparePlayback" in audio_source
    assert "await audio.preparePlayback()" not in chat_source
    assert "stopRecordingRequested" in chat_source
    assert "capturedAudioChunks" in chat_source
    assert "['starting', 'recording'].includes(microphoneState)" in voice_controls_source
    recording_block = chat_source.split("async function startRecording()", 1)[1].split(
        "async function stopRecording()", 1
    )[0]
    assert recording_block.index("audio.preparePlayback()") < recording_block.index(
        "ensureConnected()"
    )
    assert 'event.type === "session.ready"' in chat_source
    assert "buildModeSetEvent(mode.value)" in chat_source
    assert "assistantTranscript" in chat_source
    assert ':answer-text="chatApi.assistantTranscript.value"' in guide_source
    assert "avatarCaption" not in guide_source
    assert "registerProcessor" in worklet_source
    assert "16000" in worklet_source


def test_digital_human_frontend_isolated_behind_feature_entrypoint():
    feature_root = Path("frontend/src/features/digital-human")
    expected_files = (
        feature_root / "index.js",
        feature_root / "components/DigitalHumanStage.vue",
        feature_root / "components/DigitalHumanVoiceControls.vue",
        feature_root / "components/TranscriptConfirmation.vue",
        feature_root / "renderers/Live2DAvatarRenderer.vue",
        feature_root / "composables/usePcmAudio.js",
        feature_root / "lib/audioCaptureQuality.js",
        feature_root / "lib/live2dExpression.js",
        feature_root / "lib/live2dMotion.js",
        feature_root / "lib/pcmAudio.js",
    )

    assert all(path.is_file() for path in expected_files)
    feature_entrypoint = (feature_root / "index.js").read_text(encoding="utf-8")
    chat_main = Path("frontend/src/components/ChatMain.vue").read_text(encoding="utf-8")
    realtime_chat = Path("frontend/src/composables/useRealtimeChat.js").read_text(
        encoding="utf-8"
    )

    assert 'from "../features/digital-human"' in chat_main
    assert 'from "../features/digital-human"' in realtime_chat
    assert "<svg" not in chat_main
    assert "../lib/audioCaptureQuality.js" not in realtime_chat
    assert 'from "./usePcmAudio"' not in realtime_chat
    for exported_name in (
        "DigitalHumanStage",
        "DigitalHumanVoiceControls",
        "TranscriptConfirmation",
        "usePcmAudio",
        "createTailProtection",
        "createCaptureQualityTracker",
        "TAIL_PROTECTION_MS",
        "float32Metrics",
        "float32ToInt16",
        "pcmRms",
    ):
        assert exported_name in feature_entrypoint


def test_digital_human_live2d_renderer_replaces_svg_with_stable_contract():
    feature_root = Path("frontend/src/features/digital-human")
    renderer_path = feature_root / "renderers/Live2DAvatarRenderer.vue"
    svg_path = feature_root / "renderers/SvgAvatarRenderer.vue"

    assert renderer_path.is_file()
    assert not svg_path.exists()
    renderer_source = renderer_path.read_text(encoding="utf-8")
    assert "avatarId:" in renderer_source
    assert "const MODEL_URL" not in renderer_source
    assert "resolveAvatarProfile" in renderer_source
    assert "state:" in renderer_source
    assert "audioLevel:" in renderer_source
    assert "expression:" in renderer_source
    assert "transcript:" not in renderer_source
    assert "beforeModelUpdate" in renderer_source
    assert "ResizeObserver" in renderer_source
    assert 'import * as PIXI from "pixi.js"' not in renderer_source
    motion_source = (feature_root / "lib/live2dMotion.js").read_text(encoding="utf-8")
    assert "lipSyncIds" in motion_source
    assert "applyLipSyncValue" in renderer_source
    loader_source = (feature_root / "lib/live2dLoader.js").read_text(encoding="utf-8")
    assert 'import("pixi.js")' in loader_source

    stage_source = (feature_root / "components/DigitalHumanStage.vue").read_text(
        encoding="utf-8"
    )
    assert "Live2DAvatarRenderer" in stage_source
    assert "SvgAvatarRenderer" not in stage_source
    assert "emotionText" in stage_source
    assert "数字人形象加载失败" in stage_source


def test_digital_human_selector_lives_in_topbar_without_owning_realtime_state():
    feature_root = Path("frontend/src/features/digital-human")
    stage_source = (feature_root / "components/DigitalHumanStage.vue").read_text(
        encoding="utf-8"
    )
    selector_path = feature_root / "components/DigitalHumanAvatarSelector.vue"
    assert selector_path.is_file()
    selector_source = selector_path.read_text(encoding="utf-8")
    chat_main = Path("frontend/src/components/ChatMain.vue").read_text(encoding="utf-8")
    guide_view = Path("frontend/src/views/GuideView.vue").read_text(encoding="utf-8")
    realtime_chat = Path("frontend/src/composables/useRealtimeChat.js").read_text(
        encoding="utf-8"
    )

    assert "AVATAR_PROFILES" in selector_source
    assert "emit('avatar-change'" in selector_source
    assert "DigitalHumanAvatarSelector" in chat_main
    assert 'v-if="mode === \'avatar\'"' in chat_main
    assert 'class="topbar-avatar-selector"' in chat_main
    assert "AVATAR_PROFILES" not in stage_source
    assert 'class="avatar-selector"' not in stage_source
    assert "emit('avatar-change'" not in stage_source
    assert ':avatar-id="avatarId"' in stage_source
    assert "avatarId:" in chat_main
    assert '@avatar-change="emit(\'avatar-change\', $event)"' in chat_main
    assert ':avatar-id="chatApi.avatarId.value"' in guide_view
    assert '@avatar-change="chatApi.setAvatar"' in guide_view
    assert "loadAvatarPreference" in realtime_chat
    assert "saveAvatarPreference" in realtime_chat
    assert "profile.id === avatarId && !avatarReady" in selector_source

    stage_style = stage_source.split(".digital-human-stage {", 1)[1].split(
        ".avatar-loading,", 1
    )[0]
    assert "background: transparent;" in stage_style
    assert "border: 1px solid transparent;" in stage_style
    assert "backdrop-filter: none;" in stage_style
    assert "radial-gradient" not in stage_style


def test_digital_human_stage_uses_left_visual_and_latest_answer_panel():
    feature_root = Path("frontend/src/features/digital-human")
    stage_source = (feature_root / "components/DigitalHumanStage.vue").read_text(
        encoding="utf-8"
    )
    answer_panel_path = feature_root / "components/DigitalHumanAnswerPanel.vue"
    assert answer_panel_path.is_file()
    answer_panel_source = answer_panel_path.read_text(encoding="utf-8")
    assistant_answer_source = Path("frontend/src/components/AssistantAnswer.vue").read_text(
        encoding="utf-8"
    )
    chat_source = Path("frontend/src/components/ChatMain.vue").read_text(encoding="utf-8")
    guide_source = Path("frontend/src/views/GuideView.vue").read_text(encoding="utf-8")

    assert "DigitalHumanAnswerPanel" in stage_source
    assert 'class="avatar-visual"' in stage_source
    assert ':answer-text="answerText"' in stage_source
    assert "avatar-transcript" not in stage_source
    assert "width: min(980px, 100%);" in stage_source
    assert "grid-template-columns: minmax(300px, 42%) minmax(0, 58%);" in stage_source
    assert "@media (max-width: 900px)" in stage_source
    assert "grid-template-columns: 1fr;" in stage_source

    for expected_copy in (
        "向数字人提问后，回答将在这里显示。",
        "正在聆听你的问题…",
        "正在为你整理回答…",
        "正在生成回答…",
        "暂时无法生成回答，请稍后重试。",
    ):
        assert expected_copy in answer_panel_source
    assert "const STICKY_THRESHOLD = 48" in answer_panel_source
    assert "scrollHeight - scrollTop - clientHeight" in answer_panel_source
    assert "watch(() => props.answerText" in answer_panel_source
    assert "overflow-y: auto" in answer_panel_source
    assert "AssistantAnswer" in answer_panel_source
    assert '<AssistantAnswer v-if="normalizedAnswer"' in answer_panel_source
    assert "<p>{{ displayText }}</p>" not in answer_panel_source
    assert "line.match(/^#{1,6}\\s+/)" in assistant_answer_source

    assert "answerText:" in chat_source
    assert ':answer-text="answerText"' in chat_source
    assert "transcript:" not in chat_source
    assert ':answer-text="chatApi.assistantTranscript.value"' in guide_source
    assert ':transcript="chatApi.avatarCaption.value"' not in guide_source
    assert "给灵境智导发送消息，例如：给我推荐灵山胜境的游玩路线" in chat_source
    assert "灵山胜境适合老人怎么玩" not in chat_source


def test_live2d_dependencies_and_local_mao_pro_assets_are_complete():
    package = Path("frontend/package.json").read_text(encoding="utf-8")
    live2d_root = Path("frontend/public/digital-human/live2d")
    model_root = live2d_root / "mao_pro"
    model_json = model_root / "mao_pro.model3.json"

    assert '"pixi.js": "6.5.10"' in package
    assert '"pixi-live2d-display": "0.4.0"' in package
    assert (live2d_root / "live2dcubismcore.min.js").is_file()
    assert (live2d_root / "NOTICE.md").is_file()
    assert (live2d_root / "LICENSE-Live2D-Cubism-SDK.txt").is_file()
    assert (model_root / "README.md").is_file()
    assert model_json.is_file()

    model_source = model_json.read_text(encoding="utf-8")
    assert "http://" not in model_source
    assert "https://" not in model_source
    for expected_asset in (
        "mao_pro.moc3",
        "mao_pro.4096/texture_00.png",
        "mao_pro.physics3.json",
        "mao_pro.pose3.json",
        "expressions/exp_01.exp3.json",
        "expressions/exp_02.exp3.json",
        "expressions/exp_04.exp3.json",
        "expressions/exp_05.exp3.json",
    ):
        assert (model_root / expected_asset).is_file(), expected_asset


def test_local_chitose_and_haruto_runtime_assets_are_complete():
    live2d_root = Path("frontend/public/digital-human/live2d")
    expected = {
        "chitose": (
            "chitose.model3.json",
            "chitose.moc3",
            "chitose.2048/texture_00.png",
            "chitose.physics3.json",
            "chitose.pose3.json",
            "expressions/Normal.exp3.json",
            "expressions/Smile.exp3.json",
            "expressions/Sad.exp3.json",
            "expressions/Surprised.exp3.json",
        ),
        "haruto": (
            "haruto.model3.json",
            "haruto.moc3",
            "haruto.2048/texture_00.png",
            "haruto.physics3.json",
            "motion/idle.motion3.json",
        ),
    }

    for avatar_id, assets in expected.items():
        model_root = live2d_root / avatar_id
        assert (model_root / "README.md").is_file()
        model_path = model_root / assets[0]
        model = json.loads(model_path.read_text(encoding="utf-8"))
        assert "http://" not in model_path.read_text(encoding="utf-8")
        assert "https://" not in model_path.read_text(encoding="utf-8")
        for asset in assets:
            assert (model_root / asset).is_file(), f"{avatar_id}: {asset}"
        referenced_paths = _collect_live2d_runtime_paths(model["FileReferences"])
        for referenced_path in referenced_paths:
            assert (model_root / referenced_path).is_file(), f"{avatar_id}: {referenced_path}"

        if avatar_id == "haruto":
            groups = {group["Name"]: group["Ids"] for group in model["Groups"]}
            assert groups["LipSync"] == ["PARAM_MOUTH_OPEN_Y"]
            assert groups["EyeBlink"] == ["PARAM_EYE_L_OPEN", "PARAM_EYE_R_OPEN"]


def _collect_live2d_runtime_paths(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [path for item in value for path in _collect_live2d_runtime_paths(item)]
    if isinstance(value, dict):
        return [
            path
            for key, item in value.items()
            if key != "Name"
            for path in _collect_live2d_runtime_paths(item)
        ]
    return []


def test_visitor_router_exposes_five_primary_views():
    package = Path("frontend/package.json").read_text(encoding="utf-8")
    main_source = Path("frontend/src/main.js").read_text(encoding="utf-8")
    app_source = Path("frontend/src/App.vue").read_text(encoding="utf-8")

    assert '"vue-router"' in package
    assert "createRouter" in main_source
    assert 'path: "/visitor/guide"' in main_source
    assert 'path: "/visitor/explore"' in main_source
    assert 'path: "/visitor/map"' in main_source
    assert 'path: "/visitor/food"' in main_source
    assert 'path: "/visitor/feedback"' in main_source
    assert "AI 智能导游" in app_source
    assert "景点探索" in app_source
    assert "互动地图" in app_source
    assert "美食推荐" in app_source
    assert "游客反馈" in app_source
    assert "RouterView" in app_source


def test_visitor_root_uses_shared_left_sidebar_navigation():
    app_source = Path("frontend/src/App.vue").read_text(encoding="utf-8")
    page_styles = Path("frontend/src/visitor-pages.css").read_text(encoding="utf-8")

    assert "visitor-sidebar" in app_source
    assert "visitor-content-shell" in app_source
    assert "visitor-global-header" not in app_source
    assert app_source.count("visitor-sidebar-icon") == 5
    assert "grid-template-columns: 232px minmax(0, 1fr)" in page_styles
    assert "overflow-y: auto" in page_styles
    assert "@media (max-width: 820px)" in page_styles
    assert ".guide-view {\n  height: 100%;\n  min-height: 100%;\n}" in page_styles


def test_visitor_shell_uses_lake_dissolve_transition_and_caches_five_views():
    app_source = Path("frontend/src/App.vue").read_text(encoding="utf-8")
    transition_source = Path(
        "frontend/src/components/VisitorRouteTransition.vue"
    ).read_text(encoding="utf-8")
    page_styles = Path("frontend/src/route-transition.css").read_text(encoding="utf-8")

    assert 'v-slot="{ Component, route }"' in app_source
    assert "VisitorRouteTransition" in app_source
    assert "KeepAlive" in transition_source
    assert ':max="5"' in transition_source
    assert 'name="lake-dissolve"' in transition_source
    assert "lake-dissolve-enter-from" in page_styles
    assert "filter: blur(7px)" in page_styles
    assert "prefers-reduced-motion: reduce" in page_styles


def test_food_and_feedback_views_have_complete_visitor_flows():
    food_source = Path("frontend/src/views/FoodView.vue").read_text(encoding="utf-8")
    food_drawer = Path("frontend/src/components/FoodDetailDrawer.vue").read_text(encoding="utf-8")
    feedback_source = Path("frontend/src/views/FeedbackView.vue").read_text(encoding="utf-8")
    vite_config = Path("frontend/vite.config.js").read_text(encoding="utf-8")

    assert 'fetch("/api/visitor/foods")' in food_source
    assert "filterFoods" in food_source
    assert "景区内" in food_source and "周边" in food_source
    assert "FoodDetailDrawer" in food_source
    assert 'query: { food: props.food.food_id }' in food_drawer
    assert "询问 AI 导游" in food_drawer
    assert 'fetch("/api/visitor/feedback"' in feedback_source
    assert "getOrCreateVisitorId" in feedback_source
    assert "fetchWithNetworkRetry" in feedback_source
    assert "request_id" in feedback_source
    assert "待处理" in feedback_source
    assert "服务暂时无法连接，请稍后点击“刷新进度”重试。" in feedback_source
    assert '"/media/foods": "http://127.0.0.1:8000"' in vite_config


def test_map_view_supports_food_layer_and_cross_type_routes():
    map_source = Path("frontend/src/views/MapView.vue").read_text(encoding="utf-8")
    map_composable = Path("frontend/src/composables/useInteractiveMap.js").read_text(encoding="utf-8")

    assert 'fetch("/api/visitor/foods")' in map_source
    assert "normalizeFoodPlace" in map_source
    assert "route.query.food" in map_source
    assert "景点" in map_source and "美食" in map_source
    assert "place.kind === \"food\"" in map_composable
    assert 'color: "#d4a64c"' in map_composable
    assert "resize" in map_composable


def test_cached_guide_reactivates_query_questions_and_suspends_hidden_audio():
    guide_source = Path("frontend/src/views/GuideView.vue").read_text(encoding="utf-8")
    realtime_source = Path("frontend/src/composables/useRealtimeChat.js").read_text(encoding="utf-8")

    assert "onActivated" in guide_source
    assert "onDeactivated" in guide_source
    assert "consumeRouteQuestion" in guide_source
    assert "chatApi.suspendForRoute" in guide_source
    assert "function suspendForRoute" in realtime_source
    assert "audio.stopCapture()" in realtime_source
    assert "audio.clearPlayback()" in realtime_source


def test_explore_and_map_views_contain_expected_interactions():
    explore_source = Path("frontend/src/views/ExploreView.vue").read_text(encoding="utf-8")
    map_source = Path("frontend/src/views/MapView.vue").read_text(encoding="utf-8")
    drawer_source = Path("frontend/src/components/AttractionDetailDrawer.vue").read_text(encoding="utf-8")
    map_composable = Path("frontend/src/composables/useInteractiveMap.js").read_text(encoding="utf-8")

    assert 'fetch("/api/visitor/attractions")' in explore_source
    assert "推荐景点" in explore_source
    assert "在地图中查看" in drawer_source
    assert "询问 AI 导游" in drawer_source
    assert 'fetch("/api/visitor/attractions")' in map_source
    assert 'fetch(`/api/tools/map/route?' in map_source
    assert "起点和终点不能相同" in map_source
    assert "AMap.Marker" in map_composable
    assert "window._AMapSecurityConfig" in map_composable
    assert "security_js_code" in map_composable
    assert "destroy" in map_composable


def test_route_views_use_v2_summary_and_show_all_key_steps():
    guide_source = Path("frontend/src/views/GuideView.vue").read_text(encoding="utf-8")
    route_panel = Path("frontend/src/components/RoutePanel.vue").read_text(encoding="utf-8")
    timeline_source = Path("frontend/src/components/ConversationTimeline.vue").read_text(
        encoding="utf-8"
    )
    map_source = Path("frontend/src/views/MapView.vue").read_text(encoding="utf-8")

    assert "RoutePanel" not in guide_source
    assert "InlineRouteCard" in timeline_source
    assert "resolveRouteSummary" in route_panel
    assert "高德原始步骤共" in route_panel
    assert "total_step_count" in route_panel
    assert ".slice(0, 8)" not in route_panel
    assert ".slice(0, 8)" not in map_source


def test_guide_view_uses_immersive_shell_without_visitor_source_tools():
    app_shell_source = Path("frontend/src/App.vue").read_text(encoding="utf-8")
    guide_source = Path("frontend/src/views/GuideView.vue").read_text(encoding="utf-8")
    chat_source = Path("frontend/src/components/ChatMain.vue").read_text(encoding="utf-8")
    timeline_source = Path("frontend/src/components/ConversationTimeline.vue").read_text(
        encoding="utf-8"
    )
    answer_source = Path("frontend/src/components/AssistantAnswer.vue").read_text(
        encoding="utf-8"
    )
    guide_styles = Path("frontend/src/guide.css").read_text(encoding="utf-8")
    styles = Path("frontend/src/styles.css").read_text(encoding="utf-8") + guide_styles
    page_styles = Path("frontend/src/visitor-pages.css").read_text(encoding="utf-8")

    assert "useRoute" in app_shell_source
    assert "visitor-app-shell--guide" in app_shell_source
    assert 'route.path === "/visitor/guide"' in app_shell_source
    assert "SourcePanel" not in guide_source
    assert "UploadPanel" not in guide_source
    assert "tool-dock" not in guide_source
    assert "show-sources" not in guide_source
    assert "guide-background" in guide_source
    assert "history-drawer" in guide_source
    assert "historyOpen" in guide_source
    assert "toggle-history" in chat_source
    assert 'aria-label="历史会话"' in chat_source
    assert "status-pill" not in chat_source
    assert "serviceState" not in chat_source
    assert "常规模式仅请求文字输出，不产生语音输出费用" not in chat_source
    assert "quick-prompts" in timeline_source
    assert 'emit("ask", prompt)' in timeline_source
    assert "show-sources" not in timeline_source
    assert "citation-link" not in timeline_source
    assert "InlineRouteCard" in timeline_source
    assert 'items.push({ type: "source"' not in answer_source
    assert "guide-home-background.jpg" in page_styles
    assert "guide-lingshan-buddha.webp" not in guide_styles
    assert "--guide-ink: #143f46" in page_styles
    assert "--guide-accent: #2f7d78" in page_styles
    assert "--guide-gold: #d4a64c" in page_styles
    assert ".visitor-app-shell--guide .visitor-sidebar" in page_styles
    assert "background-position: 56% center" in page_styles
    assert ".history-drawer" in styles
    assert ".guide-view .composer-buttons" in styles
    assert "margin-left: auto" in styles
    topbar_mode_button_style = guide_styles.split(
        ".guide-view .mode-switch button {", 1
    )[1].split("}", 1)[0]
    assert "padding: 0 14px;" in topbar_mode_button_style
    assert "white-space: nowrap;" in topbar_mode_button_style
    assert ".history-toggle-button > span:last-child" in styles
    assert ".history-drawer .session-sidebar {\n    grid-template-rows: auto auto auto minmax(0, 1fr) auto;" in styles
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in page_styles


def test_inline_route_cards_use_lazy_independent_map_instances():
    card_path = Path("frontend/src/components/InlineRouteCard.vue")
    route_map_source = Path("frontend/src/composables/useRouteMap.js").read_text(
        encoding="utf-8"
    )

    assert card_path.is_file()
    card_source = card_path.read_text(encoding="utf-8")
    assert "findSuccessfulRouteSource" in card_source
    assert "resolveRouteSummary" in card_source
    assert "routeMap.renderRoute(summary.value)" in card_source
    assert "v-if=\"expanded\"" in card_source
    assert "onBeforeUnmount(routeMap.destroy)" in card_source

    composable_index = route_map_source.index("export function useRouteMap")
    instance_index = route_map_source.index("let amapMap = null;")
    assert instance_index > composable_index
    assert "function resolveMapElement" in route_map_source
    assert "function destroy" in route_map_source
    assert "amapMap.destroy()" in route_map_source
    assert "return { notice, renderRoute, destroy }" in route_map_source


def test_guide_background_is_a_fixed_frontend_asset():
    background = Path("frontend/public/images/guide-home-background.jpg")
    source = Path("首页背景图.jpg")
    legacy_background = Path("frontend/public/images/guide-lingshan-buddha.webp")

    assert background.is_file()
    assert background.read_bytes() == source.read_bytes()
    assert legacy_background.is_file()


def test_all_map_loaders_apply_amap_security_code_before_loading_script():
    loader_paths = (
        "frontend/src/composables/useInteractiveMap.js",
        "frontend/src/composables/useRouteMap.js",
        "frontend/static/app.js",
    )

    for loader_path in loader_paths:
        source = Path(loader_path).read_text(encoding="utf-8")
        security_index = source.index("window._AMapSecurityConfig")
        script_index = source.index("document.createElement(\"script\")", security_index)
        assert security_index < script_index
        assert "security_js_code" in source


def test_fastapi_serves_visitor_subroutes(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    explore = request_path(app, "/visitor/explore")
    map_page = request_path(app, "/visitor/map")

    assert explore.status_code == 200
    assert map_page.status_code == 200


def test_fastapi_serves_pcm_capture_worklet(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    canonical_response = request_path(app, "/digital-human/pcm-capture-worklet.js")
    compatibility_response = request_path(app, "/pcm-capture-worklet.js")

    assert canonical_response.status_code == 200
    assert compatibility_response.status_code == 200
    assert canonical_response.text == compatibility_response.text
    assert "registerProcessor" in canonical_response.text


def test_fastapi_serves_local_live2d_assets(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    models = {
        "mao_pro": ("mao_pro.model3.json", "mao_pro.moc3"),
        "chitose": ("chitose.model3.json", "chitose.moc3"),
        "haruto": ("haruto.model3.json", "haruto.moc3"),
    }
    responses = {
        avatar_id: (
            request_path(app, f"/digital-human/live2d/{avatar_id}/{model_name}"),
            request_path(app, f"/digital-human/live2d/{avatar_id}/{moc_name}"),
        )
        for avatar_id, (model_name, moc_name) in models.items()
    }
    texture = request_path(
        app, "/digital-human/live2d/mao_pro/mao_pro.4096/texture_00.png"
    )
    core = request_path(app, "/digital-human/live2d/live2dcubismcore.min.js")

    assert all(model.status_code == 200 for model, _ in responses.values())
    assert all(moc.status_code == 200 for _, moc in responses.values())
    assert texture.status_code == 200
    assert core.status_code == 200
    assert all(model.json()["Version"] == 3 for model, _ in responses.values())


def test_avatar_mode_blocks_submission_until_server_acknowledges_role():
    chat_source = Path("frontend/src/composables/useRealtimeChat.js").read_text(encoding="utf-8")
    chat_main = Path("frontend/src/components/ChatMain.vue").read_text(encoding="utf-8")

    assert "const avatarReady = computed" in chat_source
    assert "ensureAvatarReady()" in chat_source
    connect_block = chat_source.split("function connect(", 1)[1].split(
        "async function ensureConnected", 1
    )[0]
    assert "avatarSynchronized.value = false" in connect_block
    assert ':avatar-ready="chatApi.avatarReady.value"' in Path(
        "frontend/src/views/GuideView.vue"
    ).read_text(encoding="utf-8")
    assert 'avatarReady: { type: Boolean' in chat_main
    assert ':disabled="mode === \'avatar\' && !avatarReady"' in chat_main


def test_legacy_admin_assets_are_still_served(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    script_response = request_path(app, "/static/admin_documents.js")
    style_response = request_path(app, "/static/app.css")

    assert script_response.status_code == 200
    assert 'fetch("/api/admin/documents"' in script_response.text
    assert style_response.status_code == 200
    assert ".source-meta" in style_response.text


def test_scenic_intro_is_owned_by_the_app_shell_without_restyling_the_guide():
    component_path = Path(
        "frontend/src/features/scenic-intro/components/ScenicIntro.vue"
    )
    composable_path = Path(
        "frontend/src/features/scenic-intro/composables/useGuideIntro.js"
    )
    policy_path = Path("frontend/src/features/scenic-intro/lib/introPolicy.js")
    style_path = Path("frontend/src/features/scenic-intro/scenic-intro.css")

    assert component_path.is_file()
    assert composable_path.is_file()
    assert policy_path.is_file()
    assert style_path.is_file()

    app_source = Path("frontend/src/App.vue").read_text(encoding="utf-8")
    component_source = component_path.read_text(encoding="utf-8")
    composable_source = composable_path.read_text(encoding="utf-8")
    style_source = style_path.read_text(encoding="utf-8")
    package = json.loads(Path("frontend/package.json").read_text(encoding="utf-8"))

    assert "ScenicIntro" in app_source
    assert "useGuideIntro" in app_source
    assert ':inert="introVisible || undefined"' in app_source
    assert ':aria-hidden="introVisible ? \'true\' : undefined"' in app_source
    assert "遇见灵山，开启灵境" in component_source
    assert "一场风景与智慧共同展开的旅程" in component_source
    assert "开启灵境之旅" in component_source
    assert 'import("gsap")' in component_source
    assert "exitTimeline?.kill()" in component_source
    assert "prefers-reduced-motion: reduce" in style_source
    assert (
        'import scenicIntroBackground from "../../../../public/images/guide-home-background.jpg";'
        in component_source
    )
    assert ':src="scenicIntroBackground"' in component_source
    assert "sessionStorage" in composable_source
    assert package["dependencies"]["gsap"] == "^3.15.0"

    guide_source = Path("frontend/src/views/GuideView.vue").read_text(encoding="utf-8")
    chat_source = Path("frontend/src/components/ChatMain.vue").read_text(encoding="utf-8")
    assert "ScenicIntro" not in guide_source
    assert "ScenicIntro" not in chat_source
