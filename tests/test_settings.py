from pathlib import Path

from lingjing_ai.config.settings import AppSettings


def test_database_url_has_no_hardcoded_default(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = AppSettings.for_workspace(tmp_path)

    assert settings.database_url == ""


def test_settings_reads_qwen_api_configuration_from_environment(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://db.example/lingjing")
    monkeypatch.setenv("LJAPI_KEY", "test-key")
    monkeypatch.setenv("LJ_LLM_MODEL", "qwen3.7-max")
    monkeypatch.setenv("LJ_EMBEDDING_PROVIDER", "aliyun")
    monkeypatch.setenv("LJ_EMBEDDING_MODEL", "text-embedding-v4")
    monkeypatch.setenv("LJ_EMBEDDING_DIMENSIONS", "1024")

    settings = AppSettings.for_workspace(tmp_path)

    assert settings.llm_api_key == "test-key"
    assert settings.llm_model == "qwen3.7-max"
    assert settings.llm_base_url.endswith("/compatible-mode/v1")
    assert settings.embedding_provider == "aliyun"
    assert settings.embedding_model == "text-embedding-v4"
    assert settings.embedding_dimensions == 1024
    assert settings.embedding_base_url.endswith("/compatible-mode/v1")
    assert settings.embedding_api_key_env == "LJAPI_KEY"
    assert settings.embedding_api_key == "test-key"
    assert settings.agent_enabled is True
    assert settings.agent_max_steps == 4
    assert settings.agent_executor_mode == "legacy"
    assert settings.langgraph_max_loops == 1
    assert settings.langgraph_reflection_enabled is True
    assert settings.question_expansion_auto_skip is True
    assert settings.realtime_skip_question_expansion is True
    assert settings.realtime_evidence_profile == "lite"
    assert settings.realtime_reconnect_max_attempts == 3
    assert settings.realtime_reconnect_base_delay_ms == 500
    assert settings.evidence_search_cache_enabled is True
    assert settings.evidence_search_cache_ttl_seconds == 600
    assert settings.agent_fast_tool_path_enabled is True
    assert settings.agent_simple_tool_direct_answer is True
    assert settings.redis_enabled is False
    assert settings.redis_url == ""
    assert settings.redis_cache_prefix == "lingjing"
    assert settings.redis_answer_cache_ttl_seconds == 1800
    assert settings.redis_weather_cache_ttl_seconds == 600
    assert settings.redis_route_cache_ttl_seconds == 1800
    assert settings.redis_place_cache_ttl_seconds == 1800
    assert settings.agent_use_query_rewrite is True
    assert settings.agent_use_document_search is True
    assert settings.agent_use_web_search is False
    assert settings.web_search_api_key_env == "SEARCH_API_KEY"
    assert settings.source_max_chunks_per_document == 2
    assert settings.enable_question_type_templates is True
    assert settings.enable_fact_guard is True
    assert settings.enable_section_aware_chunking is True
    assert settings.kg_enabled is False
    assert settings.neo4j_database == "neo4j"
    assert settings.database_url == "postgresql://db.example/lingjing"
    assert settings.question_expansion_enabled is True
    assert settings.question_expansion_model == "qwen3.7-plus"
    assert settings.question_expansion_max_candidates == 8
    assert settings.question_expansion_top_n == 3


def test_settings_reads_map_api_from_workspace_env_file(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MAP_API", raising=False)
    monkeypatch.delenv("MAP_JS_API", raising=False)
    monkeypatch.delenv("MAP_JS_SECURITY_CODE", raising=False)
    monkeypatch.delenv("AMAP_SCENIC_NAVIGATION_RADIUS_KM", raising=False)
    (tmp_path / ".env").write_text("MAP_API=map-key-from-file\n", encoding="utf-8")

    settings = AppSettings.for_workspace(tmp_path)

    assert settings.map_api_key == "map-key-from-file"
    assert settings.map_js_api_key is None
    assert settings.map_js_security_code is None
    assert settings.amap_route_default_mode == "driving"
    assert settings.amap_scenic_navigation_radius_km == 10.0


def test_settings_reads_scenic_navigation_radius_from_environment(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AMAP_SCENIC_NAVIGATION_RADIUS_KM", "8.5")

    settings = AppSettings.for_workspace(tmp_path)

    assert settings.amap_scenic_navigation_radius_km == 8.5


def test_settings_exposes_qwen_audio_realtime_defaults(tmp_path: Path, monkeypatch):
    for name in (
        "LJ_REALTIME_MODEL",
        "LJ_REALTIME_WORKSPACE_ID",
        "LJ_REALTIME_URL",
        "LJ_REALTIME_VOICE",
        "LJ_REALTIME_VOICE_MAO_PRO",
        "LJ_REALTIME_VOICE_CHITOSE",
        "LJ_REALTIME_VOICE_HARUTO",
        "LJ_REALTIME_HISTORY_TURNS",
        "LJ_REALTIME_CONNECT_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = AppSettings.for_workspace(tmp_path)

    assert settings.realtime_model == "qwen-audio-3.0-realtime-flash"
    assert settings.realtime_workspace_id == ""
    assert settings.realtime_url == ""
    assert settings.realtime_voice == "longanqian"
    assert settings.realtime_voice_mao_pro == "longanqian"
    assert settings.realtime_voice_chitose == "longanlufeng"
    assert settings.realtime_voice_haruto == "longanxiaoxin"
    assert settings.realtime_history_turns == 6
    assert settings.realtime_connect_timeout_seconds == 15
    assert settings.asr_correction_enabled is True
    assert settings.asr_glossary_path == "config/asr_glossary.yml"
    assert settings.asr_glossary_ttl_seconds == 60


def test_settings_reads_map_js_security_code_from_environment(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MAP_JS_API", "js-map-key")
    monkeypatch.setenv("MAP_JS_SECURITY_CODE", "js-security-code")

    settings = AppSettings.for_workspace(tmp_path)

    assert settings.map_js_api_key == "js-map-key"
    assert settings.map_js_security_code == "js-security-code"
    assert settings.map_js_style == "amap://styles/normal"


def test_settings_reads_custom_map_js_style(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MAP_JS_STYLE", "amap://styles/macaron")

    settings = AppSettings.for_workspace(tmp_path)

    assert settings.map_js_style == "amap://styles/macaron"


def test_settings_reads_neo4j_configuration_from_workspace_env_file(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("KG_ENABLED", raising=False)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "KG_ENABLED=true",
                "NEO4J_URI=bolt://localhost:7687",
                "NEO4J_USER=neo4j",
                "NEO4J_PASSWORD=password",
                "NEO4J_DATABASE=lingjing",
            ]
        ),
        encoding="utf-8",
    )

    settings = AppSettings.for_workspace(tmp_path)

    assert settings.kg_enabled is True
    assert settings.neo4j_uri == "bolt://localhost:7687"
    assert settings.neo4j_user == "neo4j"
    assert settings.neo4j_password == "password"
    assert settings.neo4j_database == "lingjing"


def test_settings_reads_configuration_from_workspace_config_yml(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("KG_ENABLED", raising=False)
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.delenv("NEO4J_USER", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.delenv("NEO4J_DATABASE", raising=False)
    monkeypatch.delenv("MAP_API", raising=False)
    monkeypatch.delenv("LJAPI_KEY", raising=False)
    (tmp_path / "config.yml").write_text(
        "\n".join(
            [
                "KG_ENABLED: true",
                "NEO4J_URI: bolt://localhost:7687",
                "NEO4J_USER: neo4j",
                "NEO4J_PASSWORD: password-from-yml",
                "NEO4J_DATABASE: lingjing",
                "KG_SCHEMA_VERSION: scenic_v1",
                "KG_MAX_RELATIONS_PER_CHUNK: 8",
                "KG_ENABLE_ROUTE_RELATIONS: true",
                "KG_ENABLE_RECOMMEND_RELATIONS: true",
                "KG_ENABLE_STORY_RELATIONS: true",
                "AGENT_EXECUTOR_MODE: langgraph",
                "LANGGRAPH_MAX_LOOPS: 1",
                "LANGGRAPH_REFLECTION_ENABLED: false",
                "REDIS_ENABLED: true",
                "REDIS_URL: redis://:523@localhost:6379/0",
                "REDIS_CACHE_PREFIX: lingjing_test",
                "REDIS_ANSWER_CACHE_TTL_SECONDS: 120",
                "REDIS_WEATHER_CACHE_TTL_SECONDS: 30",
                "REDIS_ROUTE_CACHE_TTL_SECONDS: 90",
                "REDIS_PLACE_CACHE_TTL_SECONDS: 45",
                "QUESTION_EXPANSION_ENABLED: true",
                "LJ_LLM_MODEL: qwen3.7-max",
                "QUESTION_EXPANSION_MODEL: qwen3.7-plus",
                "QUESTION_EXPANSION_MAX_CANDIDATES: 8",
                "QUESTION_EXPANSION_TOP_N: 3",
                "QUESTION_EXPANSION_AUTO_SKIP: false",
                "AGENT_FAST_TOOL_PATH_ENABLED: false",
                "AGENT_SIMPLE_TOOL_DIRECT_ANSWER: false",
                "LJAPI_KEY: api-key-from-yml",
                "MAP_API: map-key-from-yml",
            ]
        ),
        encoding="utf-8",
    )

    settings = AppSettings.for_workspace(tmp_path)

    assert settings.kg_enabled is True
    assert settings.neo4j_uri == "bolt://localhost:7687"
    assert settings.neo4j_user == "neo4j"
    assert settings.neo4j_password == "password-from-yml"
    assert settings.neo4j_database == "lingjing"
    assert settings.llm_model == "qwen3.7-max"
    assert settings.kg_schema_version == "scenic_v1"
    assert settings.kg_max_relations_per_chunk == 8
    assert settings.kg_enable_route_relations is True
    assert settings.kg_enable_recommend_relations is True
    assert settings.kg_enable_story_relations is True
    assert settings.agent_executor_mode == "langgraph"
    assert settings.langgraph_max_loops == 1
    assert settings.langgraph_reflection_enabled is False
    assert settings.redis_enabled is True
    assert settings.redis_url == "redis://:523@localhost:6379/0"
    assert settings.redis_cache_prefix == "lingjing_test"
    assert settings.redis_answer_cache_ttl_seconds == 120
    assert settings.redis_weather_cache_ttl_seconds == 30
    assert settings.redis_route_cache_ttl_seconds == 90
    assert settings.redis_place_cache_ttl_seconds == 45
    assert settings.question_expansion_enabled is True
    assert settings.question_expansion_model == "qwen3.7-plus"
    assert settings.question_expansion_max_candidates == 8
    assert settings.question_expansion_top_n == 3
    assert settings.question_expansion_auto_skip is False
    assert settings.agent_fast_tool_path_enabled is False
    assert settings.agent_simple_tool_direct_answer is False
    assert settings.embedding_api_key == "api-key-from-yml"
    assert settings.map_api_key == "map-key-from-yml"


def test_settings_reads_custom_embedding_api_key_env_from_config_yml(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("LJAPI_KEY", raising=False)
    monkeypatch.delenv("CUSTOM_EMBEDDING_KEY", raising=False)
    (tmp_path / "config.yml").write_text(
        "\n".join(
            [
                "LJ_EMBEDDING_API_KEY_ENV: CUSTOM_EMBEDDING_KEY",
                "CUSTOM_EMBEDDING_KEY: custom-key-from-yml",
            ]
        ),
        encoding="utf-8",
    )

    settings = AppSettings.for_workspace(tmp_path)

    assert settings.embedding_api_key_env == "CUSTOM_EMBEDDING_KEY"
    assert settings.embedding_api_key == "custom-key-from-yml"


def test_environment_variables_override_config_yml(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEO4J_PASSWORD", "password-from-env")
    (tmp_path / "config.yml").write_text("NEO4J_PASSWORD: password-from-yml\n", encoding="utf-8")

    settings = AppSettings.for_workspace(tmp_path)

    assert settings.neo4j_password == "password-from-env"


def test_settings_only_exposes_qdrant_vector_store_directory(tmp_path: Path):
    settings = AppSettings.for_workspace(tmp_path)

    assert settings.qdrant_db_dir == tmp_path / "qdrant_db"
    assert not hasattr(settings, "chroma_db_dir")
