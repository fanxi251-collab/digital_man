from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AppSettings:
    workspace_dir: Path
    data_dir: Path
    qdrant_db_dir: Path
    logs_dir: Path
    prompt_dir: Path
    chunk_size: int = 500
    chunk_overlap: int = 80
    top_k: int = 4
    min_confidence: float = 0.18
    retrieval_mode: str = "hybrid"
    vector_top_k: int = 12
    keyword_top_k: int = 12
    rerank_top_k: int = 8
    rrf_k: int = 60
    answer_cache_enabled: bool = True
    answer_cache_max_items: int = 200
    answer_cache_ttl_seconds: int = 1800
    redis_enabled: bool = False
    redis_url: str = ""
    redis_cache_prefix: str = "lingjing"
    redis_answer_cache_ttl_seconds: int = 1800
    redis_weather_cache_ttl_seconds: int = 600
    redis_route_cache_ttl_seconds: int = 1800
    redis_place_cache_ttl_seconds: int = 1800
    vector_collection_name: str = "lingjing_scenic_knowledge"
    embedding_provider: str = "aliyun"
    embedding_model: str = "text-embedding-v4"
    embedding_dimensions: int = 1024
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_api_key_env: str = "LJAPI_KEY"
    embedding_api_key: str | None = None
    max_upload_bytes: int = 5 * 1024 * 1024
    allowed_upload_extensions: tuple[str, ...] = (".txt", ".md")
    llm_api_key: str | None = None
    llm_model: str = "qwen3.7-max"
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_timeout_seconds: int = 30
    realtime_model: str = "qwen-audio-3.0-realtime-flash"
    realtime_workspace_id: str = ""
    realtime_url: str = ""
    realtime_voice: str = "longanqian"
    realtime_voice_mao_pro: str = "longanqian"
    realtime_voice_chitose: str = "longanlufeng"
    realtime_voice_haruto: str = "longanxiaoxin"
    realtime_history_turns: int = 6
    realtime_connect_timeout_seconds: int = 15
    asr_correction_enabled: bool = True
    asr_glossary_path: str = "config/asr_glossary.yml"
    asr_glossary_ttl_seconds: int = 60
    realtime_instructions: str = (
        "你是灵境景区的AI数字人导游。只能依据系统提供的景区证据回答，"
        "语气亲切、准确；严格遵守每轮临时证据中的回答契约。"
    )
    agent_enabled: bool = True
    agent_max_steps: int = 4
    agent_executor_mode: str = "legacy"
    langgraph_max_loops: int = 1
    langgraph_reflection_enabled: bool = True
    agent_fast_tool_path_enabled: bool = True
    agent_simple_tool_direct_answer: bool = True
    agent_use_query_rewrite: bool = True
    agent_use_document_search: bool = True
    agent_use_web_search: bool = False
    web_search_api_url: str = ""
    web_search_api_key_env: str = "SEARCH_API_KEY"
    map_api_key: str | None = None
    map_js_api_key: str | None = None
    map_js_security_code: str | None = None
    amap_base_url: str = "https://restapi.amap.com"
    amap_route_default_mode: str = "driving"
    amap_scenic_navigation_radius_km: float = 10.0
    agent_use_map_tools: bool = True
    kg_enabled: bool = False
    neo4j_uri: str = ""
    neo4j_user: str = ""
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"
    database_url: str = ""
    database_schema_prefix: str = ""
    kg_schema_version: str = "scenic_v1"
    kg_max_relations_per_chunk: int = 8
    kg_enable_route_relations: bool = True
    kg_enable_recommend_relations: bool = True
    kg_enable_story_relations: bool = True
    question_expansion_enabled: bool = True
    question_expansion_model: str = "qwen3.7-plus"
    question_expansion_max_candidates: int = 8
    question_expansion_top_n: int = 3
    question_expansion_auto_skip: bool = True
    source_max_chunks_per_document: int = 2
    enable_question_type_templates: bool = True
    enable_fact_guard: bool = True
    enable_section_aware_chunking: bool = True

    @classmethod
    def for_workspace(cls, workspace_dir: Path) -> "AppSettings":
        root = Path(workspace_dir)
        workspace_env = {**_read_workspace_env(root), **_read_workspace_config_yml(root)}
        embedding_api_key_env = _env_value("LJ_EMBEDDING_API_KEY_ENV", workspace_env, "LJAPI_KEY").strip() or "LJAPI_KEY"
        return cls(
            workspace_dir=root,
            data_dir=root / "data",
            qdrant_db_dir=root / "qdrant_db",
            logs_dir=root / "logs",
            prompt_dir=root / "prompt",
            llm_api_key=_env_value("LJAPI_KEY", workspace_env),
            llm_model=_env_value("LJ_LLM_MODEL", workspace_env, "qwen3.7-max"),
            llm_base_url=os.getenv(
                "LJ_LLM_BASE_URL",
                workspace_env.get("LJ_LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            ).rstrip("/"),
            realtime_model=_env_value(
                "LJ_REALTIME_MODEL",
                workspace_env,
                "qwen-audio-3.0-realtime-flash",
            ).strip()
            or "qwen-audio-3.0-realtime-flash",
            realtime_workspace_id=_env_value("LJ_REALTIME_WORKSPACE_ID", workspace_env, "").strip(),
            realtime_url=_env_value("LJ_REALTIME_URL", workspace_env, "").strip(),
            realtime_voice=_env_value("LJ_REALTIME_VOICE", workspace_env, "longanqian").strip()
            or "longanqian",
            realtime_voice_mao_pro=_env_value(
                "LJ_REALTIME_VOICE_MAO_PRO", workspace_env, "longanqian"
            ).strip()
            or "longanqian",
            realtime_voice_chitose=_env_value(
                "LJ_REALTIME_VOICE_CHITOSE", workspace_env, "longanlufeng"
            ).strip()
            or "longanlufeng",
            realtime_voice_haruto=_env_value(
                "LJ_REALTIME_VOICE_HARUTO", workspace_env, "longanxiaoxin"
            ).strip()
            or "longanxiaoxin",
            realtime_history_turns=max(
                1,
                min(50, int(_env_value("LJ_REALTIME_HISTORY_TURNS", workspace_env, "6"))),
            ),
            realtime_connect_timeout_seconds=max(
                1,
                int(_env_value("LJ_REALTIME_CONNECT_TIMEOUT_SECONDS", workspace_env, "15")),
            ),
            asr_correction_enabled=_env_bool("LJ_ASR_CORRECTION_ENABLED", workspace_env, True),
            asr_glossary_path=_env_value(
                "LJ_ASR_GLOSSARY_PATH", workspace_env, "config/asr_glossary.yml"
            ).strip()
            or "config/asr_glossary.yml",
            asr_glossary_ttl_seconds=max(
                1,
                int(_env_value("LJ_ASR_GLOSSARY_TTL_SECONDS", workspace_env, "60")),
            ),
            embedding_provider=_env_value("LJ_EMBEDDING_PROVIDER", workspace_env, "aliyun").strip().lower()
            or "aliyun",
            embedding_model=_env_value("LJ_EMBEDDING_MODEL", workspace_env, "text-embedding-v4").strip()
            or "text-embedding-v4",
            embedding_dimensions=int(_env_value("LJ_EMBEDDING_DIMENSIONS", workspace_env, "1024")),
            embedding_base_url=os.getenv(
                "LJ_EMBEDDING_BASE_URL",
                workspace_env.get("LJ_EMBEDDING_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            ).rstrip("/"),
            embedding_api_key_env=embedding_api_key_env,
            embedding_api_key=_env_value(embedding_api_key_env, workspace_env),
            redis_enabled=_env_bool("REDIS_ENABLED", workspace_env, False),
            redis_url=_env_value("REDIS_URL", workspace_env, "").strip(),
            redis_cache_prefix=_env_value("REDIS_CACHE_PREFIX", workspace_env, "lingjing").strip() or "lingjing",
            redis_answer_cache_ttl_seconds=int(_env_value("REDIS_ANSWER_CACHE_TTL_SECONDS", workspace_env, "1800")),
            redis_weather_cache_ttl_seconds=int(_env_value("REDIS_WEATHER_CACHE_TTL_SECONDS", workspace_env, "600")),
            redis_route_cache_ttl_seconds=int(_env_value("REDIS_ROUTE_CACHE_TTL_SECONDS", workspace_env, "1800")),
            redis_place_cache_ttl_seconds=int(_env_value("REDIS_PLACE_CACHE_TTL_SECONDS", workspace_env, "1800")),
            agent_executor_mode=_env_value("AGENT_EXECUTOR_MODE", workspace_env, "legacy").strip().lower()
            or "legacy",
            langgraph_max_loops=int(_env_value("LANGGRAPH_MAX_LOOPS", workspace_env, "1")),
            langgraph_reflection_enabled=_env_bool("LANGGRAPH_REFLECTION_ENABLED", workspace_env, True),
            agent_fast_tool_path_enabled=_env_bool("AGENT_FAST_TOOL_PATH_ENABLED", workspace_env, True),
            agent_simple_tool_direct_answer=_env_bool("AGENT_SIMPLE_TOOL_DIRECT_ANSWER", workspace_env, True),
            web_search_api_url=_env_value("WEB_SEARCH_API_URL", workspace_env, "").strip(),
            web_search_api_key_env=_env_value("WEB_SEARCH_API_KEY_ENV", workspace_env, "SEARCH_API_KEY").strip()
            or "SEARCH_API_KEY",
            map_api_key=_env_value("MAP_API", workspace_env),
            map_js_api_key=_env_value("MAP_JS_API", workspace_env),
            map_js_security_code=_env_value("MAP_JS_SECURITY_CODE", workspace_env),
            amap_base_url=_env_value("AMAP_BASE_URL", workspace_env, "https://restapi.amap.com").rstrip("/"),
            amap_route_default_mode=_env_value("AMAP_ROUTE_DEFAULT_MODE", workspace_env, "driving").strip().lower()
            or "driving",
            amap_scenic_navigation_radius_km=max(
                0.1,
                float(_env_value("AMAP_SCENIC_NAVIGATION_RADIUS_KM", workspace_env, "10")),
            ),
            kg_enabled=_env_bool("KG_ENABLED", workspace_env, False),
            neo4j_uri=_env_value("NEO4J_URI", workspace_env, "").strip(),
            neo4j_user=_env_value("NEO4J_USER", workspace_env, "").strip(),
            neo4j_password=_env_value("NEO4J_PASSWORD", workspace_env, "").strip(),
            neo4j_database=_env_value("NEO4J_DATABASE", workspace_env, "neo4j").strip() or "neo4j",
            database_url=(_env_value("DATABASE_URL", workspace_env, "") or "").strip(),
            database_schema_prefix=_env_value("DATABASE_SCHEMA_PREFIX", workspace_env, "").strip() or "",
            kg_schema_version=_env_value("KG_SCHEMA_VERSION", workspace_env, "scenic_v1").strip() or "scenic_v1",
            kg_max_relations_per_chunk=int(_env_value("KG_MAX_RELATIONS_PER_CHUNK", workspace_env, "8")),
            kg_enable_route_relations=_env_bool("KG_ENABLE_ROUTE_RELATIONS", workspace_env, True),
            kg_enable_recommend_relations=_env_bool("KG_ENABLE_RECOMMEND_RELATIONS", workspace_env, True),
            kg_enable_story_relations=_env_bool("KG_ENABLE_STORY_RELATIONS", workspace_env, True),
            question_expansion_enabled=_env_bool("QUESTION_EXPANSION_ENABLED", workspace_env, True),
            question_expansion_model=_env_value("QUESTION_EXPANSION_MODEL", workspace_env, "qwen3.7-plus").strip()
            or "qwen3.7-plus",
            question_expansion_max_candidates=int(_env_value("QUESTION_EXPANSION_MAX_CANDIDATES", workspace_env, "8")),
            question_expansion_top_n=int(_env_value("QUESTION_EXPANSION_TOP_N", workspace_env, "3")),
            question_expansion_auto_skip=_env_bool("QUESTION_EXPANSION_AUTO_SKIP", workspace_env, True),
        )


def _env_value(name: str, workspace_env: dict[str, str], default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is not None:
        return value
    return workspace_env.get(name, default)


def _read_workspace_env(workspace_dir: Path) -> dict[str, str]:
    env_path = workspace_dir / ".env"
    if not env_path.is_file():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = value.strip().strip("\"'")
    return values


def _read_workspace_config_yml(workspace_dir: Path) -> dict[str, str]:
    config_path = workspace_dir / "config.yml"
    if not config_path.is_file():
        return {}

    raw_values = _load_yaml_file(config_path)
    # Keep config.yml values in the same flat key/value shape as environment variables
    # so one lookup path can serve PyCharm, scripts, and deployed environments.
    return {
        str(key): _config_value_to_string(value)
        for key, value in raw_values.items()
        if key and value is not None
    }


def _load_yaml_file(config_path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError:
        return _read_simple_yaml(config_path)

    content = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(content, dict):
        return {}
    return content


def _read_simple_yaml(config_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = value.strip().strip("\"'")
    return values


def _config_value_to_string(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip().strip("\"'")


def _env_bool(name: str, workspace_env: dict[str, str], default: bool) -> bool:
    value = _env_value(name, workspace_env)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "启用"}
