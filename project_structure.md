# 项目子目录说明

当前时间：2026-07-20  Asia/Shanghai

本文档记录灵境智导当前目录职责。项目已整理为标准 Python `src` 包结构：根目录放工程资产，后端代码统一放入 `src/lingjing_ai/`。

## 根目录

### `src/lingjing_ai/`

后端 Python 应用包，包含 FastAPI、RAG、Agent、工具、知识图谱、存储和配置代码。

新的启动入口：

```powershell
python -m uvicorn lingjing_ai.api.main:app --host 127.0.0.1 --port 8000 --reload
```

如需让脚本、测试和 IDE 稳定识别包路径，可在项目根目录执行：

```powershell
python -m pip install -e .
```

### `frontend/`

原生前端页面和静态资源。

- 站点默认入口：`/`，自动进入游客端
- 游客端统一入口：`/visitor`，包含导游、探索、地图、美食和反馈五个一级页面
- 管理端统一入口：`/admin`，自动进入游客分析总览
- 管理端资料页面：`/admin/documents`
- 管理端景点页面：`/admin/attractions`
- 管理端游客分析：`/admin/analytics`
- 管理端美食页面：`/admin/foods`
- 管理端反馈页面：`/admin/feedback`
- 静态 JS 和 CSS：`frontend/static/`
- 数字人前端模块：`frontend/src/features/digital-human/`，集中管理双角色注册表、Live2D渲染器、口型/表情规则、Haru语义动作、语音控件、PCM采集播放和音频质量逻辑。
- Live2D资源：`frontend/public/digital-human/live2d/`，包含本地Haru Greeter、Mao Pro回滚资源、Chitose运行时、Cubism Core、来源和授权说明；运行时不请求第三方模型资源。
- 数字人角色：兼容ID `mao_pro`当前显示Haru Greeter女导游，`chitose`为男导游；浏览器只保存角色ID，服务端白名单决定音色和表达约束。
- Haru语义动作：`live2dSemanticMotion.js`根据实时状态、最近游客消息、助手字幕和路线来源选择最具体的动作；`live2dMotion.js`中的互斥调度器负责同义动作轮换、单动作锁定和旧定时器隔离。Chitose暂不启用该语义动作层。
- 数字人 AudioWorklet：`frontend/public/digital-human/pcm-capture-worklet.js`；共享实时会话与协议仍保留在前端公共层。

### `data/`

原始资料和资料清单。

- `uploaded/`：前端或脚本上传后的 `.txt` / `.md` 资料。
- `document_manifest.json`：资料清单，记录文档 ID、路径、MD5、切片数等。
- `tourism_analytics_snapshot.json`：由本地 Excel 生成且不提交 Git 的游客分析快照。
- `food_images/`：保存美食推荐的本地摄影封面。
- 关系数据不存放在 `data/`，统一写入 PostgreSQL。

### PostgreSQL

关系数据通过必填的 `DATABASE_URL` 访问，并按职责拆分为 `attractions`、`conversations`、`foods`、`feedback` 四个 schema。景点、美食、历史会话和游客反馈均以 PostgreSQL 为唯一事实源。

### `qdrant_db/`

正式向量数据库目录。上传、脚本导入和重新解析资料后生成的向量数据会持久化到这里。

### `logs/`

运行日志目录，用于记录 RAG 问答、Agent 工具调用轨迹等。

### `prompt/`

Prompt 文档目录，用于维护系统提示词、RAG 回答规则、拒答规则和引用规范。

### `docs/`

项目文档目录，适合放架构说明、配置说明、缓存说明、LangGraph 说明等长期文档。

### `scripts/`

命令行辅助脚本，保留在根目录，导入 `src/lingjing_ai/` 中的后端包。

常见用途：

- 导入单个资料文件。
- 重建向量库。
- 重建知识图谱。

### `tests/`

自动化测试目录，覆盖 RAG、Agent、LangGraph、高德工具、Redis 缓存、资料管理、前端页面和脚本回归。

### `config.yml`

项目本地配置文件，用于配置大模型、高德、Redis、Neo4j、LangGraph 等能力。

### `pyproject.toml`

Python 项目配置，声明 `src` 包结构和 pytest 的 `pythonpath = ["src"]`。

### `赛题.md`

赛题原始说明文档，用于理解项目背景和竞赛要求。

## 后端包结构

### `src/lingjing_ai/api/`

FastAPI 服务入口与 HTTP 接口层。

- `main.py`：应用启动入口。
- `bootstrap.py`：组装默认 RAG 管线、Qdrant、Embedding、回答生成器和知识图谱。
- `app.py`：组装游客端、管理端、RAG、Agent、上传、地图工具、美食和反馈 API。
- `food_routes.py`：提供美食游客筛选、管理 CRUD、发布和图片管理接口。
- `feedback_routes.py`：提供匿名反馈提交、本人进度查询和管理处理接口。

### `src/lingjing_ai/rag/`

RAG 检索增强生成核心能力。

- 文本清洗与标题感知切片。
- 混合检索、重排序、来源压缩。
- Prompt 加载、问题类型识别、事实保护。
- 回答生成与格式化。

### `src/lingjing_ai/agent/`

智能体编排层，位于 RAG 和工具之上。

- 规划工具调用。
- 执行工具并合并证据。
- 支持 Legacy Executor 和 LangGraph Executor。
- 天气、路线、地点类问题支持快速通道。

### `src/lingjing_ai/tools/`

智能体可调用的白名单工具。

- RAG 搜索工具。
- 原始文档搜索工具。
- 查询改写工具。
- 高德天气、地点、路线工具。
- 知识图谱搜索工具。
- 外部 Web 搜索占位工具。
- `route_summary.py`：把高德第一推荐路线压缩为 V2 摘要，保留8—12条关键步骤和最多500个轨迹点。

### `src/lingjing_ai/realtime/`

双模式 Qwen-Audio 实时会话层。

- `conversation.py`：准备 Agent/RAG 证据、会话上下文和持久化数据。
- `answer_contract.py`：按常规/数字人及路线/非路线生成回答契约，并做确定性完整性校验。
- `session.py`：桥接浏览器和 Qwen WebSocket，管理取消、降级、音频与最终文本。
- `avatar_profiles.py`：维护双角色白名单、连接级Qwen音色和完整表达风格，避免客户端直接指定任意音色或提示词。

### `src/lingjing_ai/kg/`

知识图谱模块，用于 Neo4j 图谱抽取、存储和查询。图谱只保存稳定实体关系，不存放长篇描述、天气、票价、评论等动态或长文本信息。

### `src/lingjing_ai/services/`

跨接口复用的服务层。

- 多轮对话上下文。
- 问题扩写。
- 文档清单。
- Redis JSON 缓存封装。
- 工具意图判断。
- `food_store.py`：使用 PostgreSQL `foods` schema 管理美食、图集、封面、发布和空表种子数据。
- `feedback_store.py`：使用 PostgreSQL `feedback` schema 管理幂等反馈、游客隔离和处理状态。

### `src/lingjing_ai/storage/`

向量存储实现。

- `qdrant_vector_store.py`：正式使用的 Qdrant 本地持久化向量库。
- `vector_store.py`：JSON 向量存储，主要用于轻量测试。
- `postgres.py`：统一管理 PostgreSQL schema 连接、事务和查询辅助函数。

### `src/lingjing_ai/models/`

跨模块共享的数据模型，例如文档、chunk、source、answer 等结构。

### `src/lingjing_ai/config/`

配置定义。

- `settings.py`：集中定义工作区路径、模型配置、检索配置、Agent 配置、高德配置、Redis 配置、Neo4j 配置等。

## 当前关键数据流

```text
用户上传资料
→ data/uploaded/
→ RAG 文本清洗与切片
→ Embedding 向量化
→ qdrant_db/
→ 混合检索 / Agent 工具调用 / 知识图谱补充
→ 回答生成与格式化
→ 游客端展示
```

## 当前重要约定

- 后端代码统一放在 `src/lingjing_ai/`。
- 正式向量数据库使用 Qdrant，对应目录为 `qdrant_db/`。
- 原始资料存放在 `data/uploaded/`。
- 资料清单存放在 `data/document_manifest.json`。
- 高德 Web 服务 Key 使用 `MAP_API`。
- 高德前端 JS Key 使用 `MAP_JS_API`。
- 高德前端 JS 安全密钥使用 `MAP_JS_SECURITY_CODE`，用于满足 JS API 2.0 的安全校验。
- 阿里云大模型 API Key 使用 `LJAPI_KEY`。
- 双模式智能导游使用 `src/lingjing_ai/realtime/` 连接 Qwen-Audio Realtime；PostgreSQL `conversations` schema 是历史事实源。
- 常规模式只请求文本，数字人模式请求音频和文本，模式切换不清空会话。
- 两个数字人角色共用同一会话和历史；切换角色会取消正在录音、生成或播放的轮次，但切换本身不生成回答。
- 不再使用 Chroma。
