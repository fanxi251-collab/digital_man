# 宝塔 Compose 部署文件设计

## 目标

在项目根目录生成可上传到宝塔 Linux 面板的 `neo4j.dump`、`docker-compose.yml`、`.env` 和 `app.env`。部署采用应用、PostgreSQL、Neo4j 三容器结构，数据库数据不写入应用镜像。

## 已确认环境

- 应用镜像：`lingjing-ai:2026-07-22`，目标架构 `linux/amd64`。
- PostgreSQL：18，业务数据库为 `AgentDB`。
- Neo4j Desktop DBMS：`LJ`，版本 `2026.05.0 Enterprise`。
- 应用当前使用 Neo4j `neo4j` 数据库。
- 用户已同意服务器使用同版本 Enterprise 镜像并设置 `NEO4J_ACCEPT_LICENSE_AGREEMENT=yes`。

## 文件职责

### `neo4j.dump`

使用本机 Neo4j Desktop 随附的同版本 `neo4j-admin`，在 DBMS 已停止时离线导出 `neo4j` 数据库。dump 必须能被同版本管理工具识别，禁止创建空占位文件。

### `docker-compose.yml`

定义以下服务：

- `postgres`：固定 `postgres:18`，数据卷挂载到 PostgreSQL 18 要求的 `/var/lib/postgresql`。
- `neo4j`：固定 `neo4j:2026.05.0-enterprise`，启用许可证确认，持久化 `/data`、`/logs` 和 `/backups`。
- `app`：使用 `lingjing-ai:2026-07-22`，仅向宿主机回环地址映射 8000，通过 Docker 内部网络访问两个数据库。

Compose 包含数据库健康检查、服务启动依赖、非公开数据库端口和独立命名卷。Neo4j Browser 仅映射到宿主机 `127.0.0.1:7474`。

### `.env`

作为 Compose 插值文件，包含：

- Compose 项目名；
- PostgreSQL 用户、数据库名和密码；
- 容器内 `DATABASE_URL`；
- Neo4j 镜像版本、用户、数据库名、密码和许可证确认。

现有 `.env` 中的前端地图安全码先迁入 `app.env`，再安全替换 `.env`。数据库连接密码在 `DATABASE_URL` 中进行 URL 编码。

### `app.env`

作为应用容器环境文件，保存当前项目已有的模型、高德、知识图谱和可选服务配置。部署时强制：

- `KG_ENABLED=true`；
- `NEO4J_URI=bolt://neo4j:7687`；
- PostgreSQL 连接只由 Compose 的 `.env` 注入；
- Redis 未启用时不输出 Redis 密码或连接串。

## 密钥安全

- `.env`、`app.env`、`*.dump` 必须被 `.gitignore` 忽略。
- Docker 构建上下文继续排除所有环境文件。
- 生成和验证过程不得在终端输出密钥、完整连接串或 dump 内容。
- `docker-compose.yml` 只引用变量，不写入真实密码。

## 数据恢复顺序

1. 宝塔中加载应用、PostgreSQL 和 Neo4j 镜像。
2. 仅启动 PostgreSQL 与 Neo4j。
3. 恢复 PostgreSQL custom dump。
4. 停止 Neo4j 业务数据库并加载 `neo4j.dump`。
5. 启动应用，检查 PostgreSQL 与知识图谱状态。
6. 宝塔 Nginx 将 HTTPS 域名反向代理到 `127.0.0.1:8000`。

## 验证

- `neo4j.dump` 非空，并可由同版本 `neo4j-admin database info` 或 `database load` 预检识别。
- `docker compose config --quiet` 在变量文件存在时通过。
- Compose 中不包含真实密钥。
- 两个环境文件包含所需键但不输出键值。
- Git 确认 `.env`、`app.env` 和 `neo4j.dump` 均被忽略。
- 配置文件的 PostgreSQL 18 数据卷路径、Neo4j 版本、内部主机名和端口均与设计一致。
