# LingJing AI 比赛 Docker 镜像设计

当前时间：2026-07-20 11:49:08 +08:00（Asia/Shanghai）

## 1. 目标

为 LingJing AI 生成一个可离线导入、启动后即可查看完整演示数据的 Linux/amd64 Docker 镜像，并导出为 `lingjing-ai-competition-amd64.tar` 供比赛上传或现场部署。

镜像负责运行 Vue 游客端、原生管理端和 FastAPI 后端。阿里云、高德等第三方服务密钥不得写入镜像，必须由运行者通过环境变量注入。

## 2. 方案选择

采用单应用镜像，不在镜像中捆绑 Redis 或 Neo4j 服务。

选择理由：

- 比赛交付只需一个镜像归档，导入和启动步骤最少。
- 本项目的 Redis 是可选缓存，缺失时会自动降级到内存缓存。
- Neo4j 是可选知识图谱增强，缺失时基础 RAG 和游客功能仍可运行。
- 避免在一个容器内管理多个服务进程，也避免提交多个体积较大的第三方镜像。

如比赛明确要求展示 Redis 或 Neo4j，可在后续另行提供 Compose 增强包，不改变本次单镜像交付物。

## 3. 构建架构

使用多阶段 Dockerfile：

1. 前端阶段使用 Node.js 20 镜像，复制 `frontend/package.json` 和锁文件，执行 `npm ci`，再复制前端源码并执行 `npm run test`、`npm run build`。
2. Python 阶段使用 Python 3.12 slim 镜像，安装项目及当前后端所需的完整运行依赖。
3. 将后端源码、脚本、Prompt、配置词典、前端管理页面、静态资源、Live2D 资源和前端构建产物复制到运行镜像。
4. 将当前演示数据与本地 Qdrant 数据复制到运行镜像。
5. 以非 root 用户运行单个 Uvicorn worker，监听 `0.0.0.0:8000`。

运行入口固定为：

```text
python -m uvicorn lingjing_ai.api.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Docker 工作目录固定为 `/app`，与项目通过 `Path.cwd()` 解析工作区的逻辑保持一致。

## 4. 镜像内置内容

镜像包含：

- `src/lingjing_ai/` 后端源码与资源。
- `frontend/dist/` Vue 生产构建产物。
- `frontend/static/` 和管理端 HTML。
- `frontend/public/digital-human/` 的 Live2D、Cubism Core 和 PCM Worklet 资源。
- `prompt/`、`config/asr_glossary.yml`。
- `scripts/` 中的运维脚本。
- `data/uploaded/` 与 `data/document_manifest.json`。
- `data/conversations.db`、`data/attractions.db`、`data/foods.db`、`data/feedback.db`。
- `data/attraction_images/`、`data/food_images/` 和 `data/tourism_analytics_snapshot.json`。
- `qdrant_db/` 当前可用的本地向量库。
- Docker 比赛运行说明。

镜像内数据是构建时快照。容器启动后的修改默认只存在于容器可写层；需要保留新增数据时，运行者可为 `/app/data` 和 `/app/qdrant_db` 挂载命名卷。

## 5. 构建上下文排除项

新增 `.dockerignore`，明确排除：

- `.git/`、`.idea/`、`.agents/`、`.superpowers/`。
- `.env`、`config.yml` 和其他本地密钥文件。
- `frontend/node_modules/`、现有 `frontend/dist/`，由构建阶段重新生成。
- Python 缓存、pytest 缓存及所有 `.pytest_tmp*` 目录。
- 日志、评测报告、探针数据库和临时下载目录。
- 原始 Live2D 制作工程、PSD、Excel 原始数据等运行时不需要的大文件。
- 已导出的 Docker tar 文件，避免递归进入构建上下文。

不会执行任何批量删除；排除项仅控制发送给 Docker 的构建上下文。

## 6. 配置和密钥

镜像默认设置：

```text
PYTHONUNBUFFERED=1
PYTHONDONTWRITEBYTECODE=1
REDIS_ENABLED=false
KG_ENABLED=false
```

完整 AI 能力运行时需要注入：

- `LJAPI_KEY`
- `MAP_API`
- `MAP_JS_API`
- `MAP_JS_SECURITY_CODE`

可选注入 Realtime 模型、Workspace ID、Redis、Neo4j 和模型覆盖配置。镜像、Dockerfile、运行说明和导出的 tar 中都不得出现本地真实密钥值。

由于当前 Qdrant 数据使用既有 Embedding 配置生成，运行时应保持相同的 `LJ_EMBEDDING_MODEL` 和 `LJ_EMBEDDING_DIMENSIONS`。完整问答体验应提供有效的 `LJAPI_KEY`。

## 7. 健康检查与运行

镜像声明 8000 端口，并使用 Python 标准库请求 `/visitor` 作为健康检查，不额外安装 curl。

基本运行命令：

```text
docker run --name lingjing-ai -p 8000:8000 --env-file competition.env lingjing-ai:competition
```

使用命名卷持久化：

```text
docker run --name lingjing-ai -p 8000:8000 --env-file competition.env -v lingjing-data:/app/data -v lingjing-qdrant:/app/qdrant_db lingjing-ai:competition
```

首次挂载新的命名卷时，Docker 会以镜像内对应目录的演示数据初始化卷。

## 8. 错误处理

- 缺少阿里云 Key：应用仍可启动并展示静态页面和本地数据，实时语音与完整 LLM 能力不可用。
- 缺少高德 Key：地图配置接口返回未启用状态，景点、美食、资料和基础页面仍可访问。
- Redis 或 Neo4j 不可用：按项目现有逻辑降级，不阻塞容器启动。
- Qdrant 被多进程打开：镜像强制使用单 worker，运行说明禁止同一数据卷被多个容器同时挂载写入。
- 前端构建或测试失败：Docker 构建直接失败，不产出比赛镜像。
- Python 依赖安装失败：Docker 构建直接失败并保留构建日志。

## 9. 验证标准

构建前：

- Python 编译检查通过。
- 后端完整 pytest 通过。
- 前端 Node 测试通过。
- 工作区不存在 Git 未解决冲突。

镜像构建后：

- 镜像架构为 `linux/amd64`。
- 容器健康状态变为 healthy。
- `/visitor`、`/visitor/guide` 返回 200 且使用生产构建页面。
- 管理端资料、景点、美食、反馈和分析页面返回 200。
- 资料、景点、美食、反馈与知识图谱状态 API 返回可解析响应。
- 内置资料、景点和美食数量不为零。
- 镜像环境与文件系统中不存在构建机的真实 `.env` 或 `config.yml`。
- 容器以非 root 用户运行。

导出后：

- `docker save` 生成 `lingjing-ai-competition-amd64.tar`。
- 记录文件大小和 SHA-256。
- 使用 `docker image inspect` 记录镜像 ID、架构和入口。

## 10. 交付物

- `Dockerfile`
- `.dockerignore`
- `docs/Docker比赛镜像运行说明.md`
- `lingjing-ai-competition-amd64.tar`
- 构建与验证结果摘要

不创建或提交包含真实密钥的 `competition.env`；运行说明只提供占位模板。
