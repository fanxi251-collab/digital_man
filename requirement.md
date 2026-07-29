# 灵境智导项目环境要求

当前时间：2026-07-12  Asia/Shanghai

## 1. 基础运行环境

- 操作系统：Windows 10/11 推荐；Linux/macOS 也可运行，但命令需按系统调整。
- Python：`>= 3.10`，推荐使用 Conda 独立环境。
- Node.js：推荐 `>= 20`，当前已验证环境为 `v24.15.0`。
- npm：推荐 `>= 10`，当前已验证环境为 `11.12.1`。
- 项目使用标准 Python `src` 包结构，建议在项目根目录执行：

```powershell
python -m pip install -e .
```

## 2. Python 依赖

项目当前没有单独的 `requirements.txt`，接手开发者可先在 Conda 环境中安装以下依赖：

```powershell
python -m pip install fastapi "uvicorn[standard]" python-multipart pydantic httpx qdrant-client PyYAML pytest openpyxl
```

如果启用完整增强能力，继续安装：

```powershell
python -m pip install redis neo4j langgraph
```

依赖说明：

- `fastapi`、`uvicorn[standard]`：后端 API 服务。
- `python-multipart`：资料上传接口需要。
- `pydantic`：API 请求/响应模型。
- `httpx`：阿里云 embedding、高德地图等 HTTP 调用。
- `qdrant-client`：本地 Qdrant 向量数据库，数据目录为 `qdrant_db/`。
- `PyYAML`：读取 `config.yml`；未安装时项目有简易 YAML 读取兜底，但推荐安装。
- `pytest`：测试。
- `openpyxl`：以只读模式校验旅游行为 Excel 并生成固定分析快照。
- `redis`：启用 Redis 缓存时需要。
- `neo4j`：启用知识图谱时需要。
- `langgraph`：`AGENT_EXECUTOR_MODE=langgraph` 时需要。

## 3. 前端依赖

游客端已迁移为 Vue 3 + Vite，前端依赖在 `frontend/package.json` 中：

- `vue`
- `vite`
- `@vitejs/plugin-vue`

首次安装和构建：

```powershell
cd frontend
npm install
npm run build
```

开发模式：

```powershell
cd frontend
npm run dev
```

说明：

- `/visitor` 会优先加载 `frontend/dist/index.html`。
- 如果未执行 `npm run build`，后端会显示“Vue 游客端尚未构建”的提示页。
- `frontend/node_modules/` 和 `frontend/dist/` 是生成目录，不需要提交。

## 4. 配置文件与密钥

项目根目录使用 `config.yml` 或 `.env` 读取配置，也支持系统环境变量覆盖。

常用配置项：

```yaml
LJAPI_KEY: 你的阿里云百炼/DashScope API Key
LJ_LLM_MODEL: qwen3.7-max
QUESTION_EXPANSION_MODEL: qwen3.7-plus
LJ_REALTIME_MODEL: qwen-audio-3.0-realtime-flash
LJ_REALTIME_WORKSPACE_ID: 可选的北京地域 Workspace ID
LJ_REALTIME_VOICE: longanqian
LJ_REALTIME_HISTORY_TURNS: 6
LJ_REALTIME_CONNECT_TIMEOUT_SECONDS: 15

MAP_API: 你的高德 Web 服务 Key
MAP_JS_API: 你的高德 JS API Key
MAP_JS_SECURITY_CODE: 与高德 JS API Key 配套的安全密钥

AGENT_EXECUTOR_MODE: legacy 或 langgraph

REDIS_ENABLED: true
REDIS_URL: redis://:523@localhost:6379/0

KG_ENABLED: true
NEO4J_URI: bolt://localhost:7687
NEO4J_USER: neo4j
NEO4J_PASSWORD: 你的 Neo4j 密码
NEO4J_DATABASE: neo4j
```

注意：

- `config.yml`、`.env` 通常包含密钥，不建议提交到公开仓库。
- 如果没有安装 `langgraph`，请把 `AGENT_EXECUTOR_MODE` 改为 `legacy`。
- 如果没有启动 Neo4j，请把 `KG_ENABLED` 改为 `false`。
- 如果没有启动 Redis，请把 `REDIS_ENABLED` 改为 `false`。

## 5. 外部服务要求

### 阿里云大模型

用于：

- 主问答模型：`qwen3.7-max`
- 问题扩写模型：`qwen3.7-plus`
- Embedding：`text-embedding-v4`
- 游客端双模式最终回答：`qwen-audio-3.0-realtime-flash`

需要配置：

```yaml
LJAPI_KEY: 你的阿里云 API Key
LJ_REALTIME_MODEL: qwen-audio-3.0-realtime-flash
```

实时会话的完整配置与事件说明见 `docs/qwen_audio_realtime.md`。

### 高德地图

用于：

- 天气查询
- 地点查询
- 步行/驾车路线规划
- 前端路线地图绘制

需要配置：

```yaml
MAP_API: 高德 Web 服务 Key
MAP_JS_API: 高德 JS API Key
MAP_JS_SECURITY_CODE: 与高德 JS API Key 配套的安全密钥
```

`MAP_API` 仅由后端调用高德 Web 服务；`MAP_JS_API` 和 `MAP_JS_SECURITY_CODE`
用于浏览器加载地图 JS API。安全密钥不应写入源码或提交到 Git。

### Redis

用于：

- 问答缓存
- 天气缓存
- 路线缓存
- 地点缓存

当前项目配置示例：

```yaml
REDIS_ENABLED: true
REDIS_URL: redis://:523@localhost:6379/0
```

连接测试：

```powershell
redis-cli -a 523 ping
```

返回 `PONG` 即可。

### Neo4j

用于：

- 知识图谱增强检索
- 路线、推荐、深度讲解等实体关系推理

当前项目配置示例：

```yaml
KG_ENABLED: true
NEO4J_URI: bolt://localhost:7687
NEO4J_USER: neo4j
NEO4J_PASSWORD: 你的密码
NEO4J_DATABASE: neo4j
```

如果不需要知识图谱，可关闭：

```yaml
KG_ENABLED: false
```

## 6. 数据目录说明

- `data/uploaded/`：上传的原始 `.txt` / `.md` 资料。
- `data/document_manifest.json`：资料清单。
- `data/attraction_images/`、`data/food_images/`：景点和美食图片文件。
- PostgreSQL：通过 `DATABASE_URL` 保存景点、美食、游客反馈和历史会话关系数据。
- `qdrant_db/`：Qdrant 本地向量库。
- `logs/`：问答、Agent 等运行日志。
- `frontend/dist/`：Vue 构建产物。
- `frontend/node_modules/`：前端依赖目录。

这些多为运行生成目录，迁移项目时需要根据目标开发者是否要复现现有数据来决定是否一并拷贝。

## 7. 启动命令

在项目根目录启动后端：

```powershell
python -m uvicorn lingjing_ai.api.main:app --host 127.0.0.1 --port 8000 --reload
```

访问地址：

```text
游客端：http://127.0.0.1:8000/visitor
管理端：http://127.0.0.1:8000/admin
```

脚本导入资料：

```powershell
python scripts/import_document.py data/uploaded/你的资料.md --workspace .
```

重建向量库：

```powershell
python scripts/rebuild_vector_store.py --workspace .
```

重建知识图谱：

```powershell
python scripts/rebuild_knowledge_graph.py --workspace .
```

刷新景点种子封面（Git 更新了 `src/lingjing_ai/assets/attractions/seed-*.webp` 后）：

```powershell
python scripts/refresh_attraction_seed_covers.py --workspace .
```

说明：空库首次启动会自动播种；已有库若仍使用默认 `seed-*.webp` 封面，重启后端时会自动同步 Git 中的新图。管理端上传的自定义封面不会被覆盖。上面的脚本仅用于强制恢复八个默认景点的仓库封面。详见 `src/lingjing_ai/assets/attractions/README.md`。

## 8. 验证命令

Python 编译检查：

```powershell
python -m compileall -q src scripts tests
```

后端测试：

```powershell
python -m pytest -q
```

前端构建：

```powershell
cd frontend
npm run build
```

当前最近一次后端回归结果：

```text
152 passed
```

## 9. 交接建议

建议交给其他开发者时同时提供：

- 项目源码。
- `config.yml` 示例文件，但不要直接泄露真实 API Key。
- 是否需要一并提供 `data/uploaded/`、`data/document_manifest.json`、图片目录和 `qdrant_db/`，以及 PostgreSQL `pg_dump` 备份。
- Redis、Neo4j 是否必须启用；如果不是必须，建议先关闭后启动项目。
- 前端首次运行前必须执行 `npm install` 和 `npm run build`。
- 景点封面种子图在 `src/lingjing_ai/assets/attractions/`；运行时图在 `data/attraction_images/`（勿提交）。同事拉取新 seed 后重启后端即可自动同步默认封面；自定义封面不受影响。
