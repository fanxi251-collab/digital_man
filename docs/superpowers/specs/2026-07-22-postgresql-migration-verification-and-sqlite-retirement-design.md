# PostgreSQL 数据补迁与 SQLite 退役设计

当前时间：2026-07-22 09:55:26 +08:00（Asia/Shanghai）

## 1. 目标与范围

本次工作先把 PostgreSQL 确立为项目唯一业务数据库，再移除当前工作区内所有 SQLite 运行代码、测试假设、数据库文件和现行说明。任何删除动作都必须发生在数据备份、精确补迁和全量校验均成功之后。

本设计覆盖当前主工作区，不处理 `.worktrees/` 中其他 Git 工作树。项目中与 PostgreSQL 迁移无关的业务功能保持不变；全项目审计发现的独立架构重构会单独设计，避免与数据迁移混合实施。

## 2. 当前核验结论

只读核验已扫描当前 PostgreSQL 数据库的全部非系统 schema，数据库只有 `attractions`、`conversations`、`feedback`、`foods` 四个业务 schema，共 8 张表，没有发现数据被迁移到其他位置。

| 数据 | SQLite | PostgreSQL | 结论 |
| --- | ---: | ---: | --- |
| 会话 | 5 | 0 | 未迁移 |
| 聊天消息 | 100 | 0 | 未迁移 |
| 已完成实时轮次 | 46 | 0 | 未迁移 |
| 游客反馈 | 2 | 0 | 未迁移 |
| 景点 | 8 | 8 | 业务字段相同，主键和时间不同 |
| 景点图片 | 8 | 8 | 业务字段相同，主键不同 |
| 美食 | 6 | 6 | 业务字段相同，主键和时间不同 |
| 美食图片 | 6 | 6 | 业务字段相同，主键不同 |

`frontend/data/conversations.db` 是一个空库，但仍被 Git 跟踪。`data/` 下四个 SQLite 文件被 `.gitignore` 忽略，却仍会进入当前 Docker 构建上下文和运行镜像。

## 3. 安全边界

迁移开始前停止所有可能写入四个 PostgreSQL schema 的应用、脚本和测试进程。迁移工具必须确认目标数据库身份、目标 schema 集合和预期表名，不接受通配 schema，也不得操作系统 schema。

备份分为两类：

1. 使用 `pg_dump` 对四个 PostgreSQL schema 生成带时间戳的自定义格式备份。
2. 把五个 SQLite 源文件逐个复制到工作区外的专用备份目录，保留原始迁移来源。

所有迁移写入在同一个 PostgreSQL 事务中完成。迁移前重新读取源和目标摘要；若目标数据与本设计记录的安全状态不一致，立即中止，不覆盖运行期间新增的数据。事务失败时必须整体回滚。

## 4. 精确补迁策略

迁移采用一次性工作区外工具，仓库中不保留 SQLite 读取代码。

迁移顺序遵守外键关系：

1. 会话：`conversation_sessions` → `chat_messages` → `completed_realtime_turns`。
2. 反馈：`visitor_feedback`。
3. 景点：以 SQLite 的原始 `attraction_id`、`image_id` 和时间字段替换当前重新播种的数据。
4. 美食：以 SQLite 的原始 `food_id`、`image_id` 和时间字段替换当前重新播种的数据。

景点和美食只允许在“业务键集合和排除主键、时间后的字段完全相同”时执行精确替换。若 PostgreSQL 出现额外业务记录、字段差异或关联关系异常，迁移必须中止并报告差异。

带自增键的表写入原始 ID 后，需要把 PostgreSQL sequence 调整到当前最大值，避免后续插入发生主键冲突。

## 5. 全量校验与删除门槛

迁移提交后重新执行独立只读校验，逐表检查：

- 字段集合一致；
- 记录数一致；
- 主键集合一致；
- 外键引用完整；
- 对规范化后的整行数据计算 SHA-256，SQLite 与 PostgreSQL 摘要一致；
- PostgreSQL sequence 的下一值大于现有最大自增 ID；
- 四个 PostgreSQL 存储测试通过；
- API 会话、景点、美食和反馈测试通过。

任一检查失败时，不删除 SQLite 文件或说明。只有全部检查通过，才逐个删除以下当前工作区文件：

- `data/attractions.db`
- `data/conversations.db`
- `data/feedback.db`
- `data/foods.db`
- `frontend/data/conversations.db`

删除必须一次针对一个明确路径，不使用递归、通配符或批量删除命令。工作区外的迁移备份保留到用户完成 Docker 部署验收。

## 6. 代码与配置清理

PostgreSQL 成为强制依赖：

- `AppSettings` 不再提供含账号和密码的 `DATABASE_URL` 默认值；缺少连接配置时启动应给出清晰错误。
- 保留统一 PostgreSQL 连接模块，清除运行代码中的 SQLite 导入、类型、路径和注释。
- 测试不再使用硬编码 PostgreSQL 凭据，也不让与数据库无关的单元测试自动创建四个 schema。
- 数据库测试使用显式测试配置和随机 schema 隔离，并在测试结束后只清理本次测试创建的明确 schema。
- `.gitignore`、`.dockerignore` 和 Dockerfile 不再依赖 SQLite 数据快照；Docker 运行时必须通过 `DATABASE_URL` 连接外部 PostgreSQL。
- 更新项目结构、部署、会话、实时语音、需求和资源说明中的 SQLite 表述。

不会删除仍承载文档、图片、分析快照和上传资料的 `data/` 目录。

## 7. Docker 部署约束

应用镜像不内置 PostgreSQL。容器必须通过环境变量获得 `DATABASE_URL`，并确保该地址从容器网络可访问；Linux 服务器上不能把宿主机 PostgreSQL 写成容器内的 `localhost`。

Docker 构建验证应确认：

- 镜像中不存在 `.db` 文件；
- 镜像中不存在真实 `.env`、`config.yml` 或数据库密码；
- 容器在缺少 `DATABASE_URL` 时快速失败并给出明确配置错误；
- 配置有效时 `/visitor` 健康检查通过；
- PostgreSQL 数据不使用 Docker 数据卷重复保存，`data/` 卷只保存图片、上传资料和其他文件资产。

## 8. 全项目审计边界

SQLite 退役完成后，对 `src/`、`scripts/`、`frontend/src/`、测试、Docker 配置和现行文档执行全量引用扫描、Python 编译、后端测试、前端测试和前端构建。只修复有明确证据的错误、失效分支、重复依赖和迁移残留。

超过 800 行且职责混杂的文件会记录为独立重构候选；除非它直接阻碍 PostgreSQL 迁移或 Docker 构建，本轮不把大规模文件拆分与数据迁移混在同一变更中。

## 9. 回滚与验收

迁移提交后若应用验收失败，停止应用并使用迁移前的 `pg_dump` 恢复四个 schema；SQLite 源备份在验收完成前不删除。

最终验收条件：

1. PostgreSQL 与 SQLite 备份的逐表数据完全一致。
2. 当前工作区和构建镜像不存在 SQLite 数据库文件。
3. 运行代码、测试配置和现行说明不再引用 SQLite。
4. 数据库/API 测试、后端完整测试、前端测试和 Docker 构建均有最新验证结果。
5. 所有改动记录在 `daily-modify/2026-07-22.md`，并明确列出未解决事项。
