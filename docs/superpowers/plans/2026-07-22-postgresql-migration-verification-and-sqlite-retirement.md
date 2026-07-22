# PostgreSQL Migration Verification and SQLite Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 精确迁移当前 SQLite 原始数据到 PostgreSQL，验证逐表完全一致后退役项目内全部 SQLite 文件、代码假设和说明，并完成 Docker 构建前的全项目审计。

**Architecture:** 数据操作分为只读预检、双重备份、单事务精确迁移和独立只读复核四层；任何一层失败都阻断下一层。仓库最终只保留 PostgreSQL 运行路径，一次性 SQLite 迁移工具与原始数据库备份放在工作区外，测试通过显式随机 schema 隔离而不污染业务 schema。

**Tech Stack:** Python 3.12、psycopg 3、PostgreSQL 18 工具、SQLite 只读迁移源、pytest、FastAPI、Vue/Vite、Docker Buildx。

## Global Constraints

- PostgreSQL 是唯一业务数据库，仓库最终不得保留 SQLite 运行代码或 `.db` 文件。
- 不处理 `.worktrees/` 中其他 Git 工作树。
- 不使用递归、通配符或批量删除命令；每个文件仅通过明确路径单独删除。
- 所有 PostgreSQL 数据替换必须在一个事务内完成，失败时整体回滚。
- 目标数据与已记录安全状态不一致时必须中止，不能覆盖新增数据。
- 工作区外 SQLite 与 PostgreSQL 备份保留到 Docker 部署验收完成。
- 生产配置必须通过 `DATABASE_URL` 注入，代码和测试不得包含真实账号或密码。
- 单个代码文件最好不超过 800 行；与迁移无关的大规模拆分另立设计。

---

### Task 1: 建立迁移前证据与双重备份

**Files:**
- Read: `data/attractions.db`
- Read: `data/conversations.db`
- Read: `data/feedback.db`
- Read: `data/foods.db`
- Read: `frontend/data/conversations.db`
- Create outside workspace: `C:/tmp/lingjing-postgres-migration-20260722/`

**Interfaces:**
- Consumes: `AppSettings.for_workspace(Path.cwd()).database_url`。
- Produces: PostgreSQL custom dump、五个 SQLite 源副本、迁移前统计摘要。

- [ ] **Step 1: 确认不存在写入进程**

Run:

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'uvicorn|pytest|rebuild_|migrate_sqlite' } |
  Select-Object ProcessId, Name, CommandLine
```

Expected: 不存在正在使用当前项目或四个业务 schema 的 Uvicorn、pytest、重建或迁移进程；若存在则停止本任务并报告明确 PID，不主动终止进程。

- [ ] **Step 2: 创建工作区外专用备份目录**

Run:

```powershell
New-Item -ItemType Directory -Path C:\tmp\lingjing-postgres-migration-20260722
```

Expected: 目录创建成功；若已存在则改用带当前 `HHmmss` 的全新明确目录，不覆盖旧备份。

- [ ] **Step 3: 逐个复制五个 SQLite 源文件**

Run each command separately:

```powershell
Copy-Item -LiteralPath data\attractions.db -Destination C:\tmp\lingjing-postgres-migration-20260722\attractions.db
Copy-Item -LiteralPath data\conversations.db -Destination C:\tmp\lingjing-postgres-migration-20260722\conversations.db
Copy-Item -LiteralPath data\feedback.db -Destination C:\tmp\lingjing-postgres-migration-20260722\feedback.db
Copy-Item -LiteralPath data\foods.db -Destination C:\tmp\lingjing-postgres-migration-20260722\foods.db
Copy-Item -LiteralPath frontend\data\conversations.db -Destination C:\tmp\lingjing-postgres-migration-20260722\frontend-conversations.db
```

Expected: 五个备份文件大小分别与源文件一致。

- [ ] **Step 4: 导出四个 PostgreSQL schema**

Run:

```powershell
$migrationDsn = python -c "import sys; from pathlib import Path; sys.path.insert(0, 'src'); from lingjing_ai.config.settings import AppSettings; print(AppSettings.for_workspace(Path.cwd()).database_url)"
pg_dump --dbname=$migrationDsn --format=custom --schema=attractions --schema=conversations --schema=feedback --schema=foods --file=C:\tmp\lingjing-postgres-migration-20260722\before-migration.dump
```

Expected: `pg_dump` exit code 0，dump 文件非空；终端摘要不得打印 DSN。

- [ ] **Step 5: 记录备份哈希**

Run:

```powershell
Get-FileHash C:\tmp\lingjing-postgres-migration-20260722\attractions.db -Algorithm SHA256
Get-FileHash C:\tmp\lingjing-postgres-migration-20260722\conversations.db -Algorithm SHA256
Get-FileHash C:\tmp\lingjing-postgres-migration-20260722\feedback.db -Algorithm SHA256
Get-FileHash C:\tmp\lingjing-postgres-migration-20260722\foods.db -Algorithm SHA256
Get-FileHash C:\tmp\lingjing-postgres-migration-20260722\frontend-conversations.db -Algorithm SHA256
Get-FileHash C:\tmp\lingjing-postgres-migration-20260722\before-migration.dump -Algorithm SHA256
```

Expected: 六个文件均产生 SHA-256。

### Task 2: 用测试驱动实现一次性精确迁移工具

**Files:**
- Create outside workspace: `C:/tmp/lingjing-postgres-migration-20260722/migrate_sqlite_to_postgres.py`
- Create outside workspace: `C:/tmp/lingjing-postgres-migration-20260722/test_migrate_sqlite_to_postgres.py`

**Interfaces:**
- Consumes: 五个 SQLite 备份路径、`DATABASE_URL`、固定 schema/table 白名单。
- Produces: `audit(dsn, sources) -> AuditReport`、`migrate(dsn, sources) -> AuditReport`；日志只输出表名、行数和哈希。

- [ ] **Step 1: 写出迁移核心的失败测试**

```python
from migrate_sqlite_to_postgres import canonical_digest, validate_target_state


def test_canonical_digest_is_order_independent():
    left = [{"id": 2, "name": "b"}, {"id": 1, "name": "a"}]
    right = list(reversed(left))
    assert canonical_digest(left, ("id",)) == canonical_digest(right, ("id",))


def test_validate_target_state_rejects_unexpected_business_rows():
    sqlite_rows = [{"name": "灵山大佛", "id": "old"}]
    postgres_rows = [
        {"name": "灵山大佛", "id": "new"},
        {"name": "新增景点", "id": "extra"},
    ]
    try:
        validate_target_state(sqlite_rows, postgres_rows, "name", {"id"})
    except RuntimeError as exc:
        assert "unexpected PostgreSQL business rows" in str(exc)
    else:
        raise AssertionError("unsafe target state was accepted")
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```powershell
python -m pytest C:\tmp\lingjing-postgres-migration-20260722\test_migrate_sqlite_to_postgres.py -q
```

Expected: import 或函数缺失导致测试失败。

- [ ] **Step 3: 实现规范化、预检、事务迁移和复核**

The temporary module must define these exact constants and functions:

```python
SCHEMA_TABLES = {
    "attractions": ("attractions", "attraction_images"),
    "conversations": (
        "conversation_sessions",
        "chat_messages",
        "completed_realtime_turns",
    ),
    "feedback": ("visitor_feedback",),
    "foods": ("foods", "food_images"),
}

PRIMARY_KEYS = {
    "attractions.attractions": ("attraction_id",),
    "attractions.attraction_images": ("image_id",),
    "conversations.conversation_sessions": ("session_id",),
    "conversations.chat_messages": ("message_id",),
    "conversations.completed_realtime_turns": ("turn_id",),
    "feedback.visitor_feedback": ("feedback_id",),
    "foods.foods": ("food_id",),
    "foods.food_images": ("image_id",),
}

def canonical_digest(rows: list[dict], primary_key: tuple[str, ...]) -> str:
    ordered = sorted(rows, key=lambda row: tuple(str(row[key]) for key in primary_key))
    payload = json.dumps(ordered, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def validate_target_state(
    sqlite_rows: list[dict],
    postgres_rows: list[dict],
    business_key: str,
    excluded_columns: set[str],
) -> None:
    sqlite_map = {str(row[business_key]): {k: v for k, v in row.items() if k not in excluded_columns} for row in sqlite_rows}
    postgres_map = {str(row[business_key]): {k: v for k, v in row.items() if k not in excluded_columns} for row in postgres_rows}
    if set(postgres_map) - set(sqlite_map):
        raise RuntimeError("unexpected PostgreSQL business rows")
    if sqlite_map != postgres_map:
        raise RuntimeError("PostgreSQL seed data differs from SQLite source")
```

The same module must also:

- open every SQLite file with URI `mode=ro`;
- connect through `psycopg` with `dict_row`;
- verify exactly the four schema names and eight table names above;
- require PostgreSQL conversations and feedback counts to remain zero before migration;
- require attractions/foods semantic projections to match before replacement;
- lock all eight tables inside one transaction;
- delete child rows before parent rows using explicit table identifiers;
- insert every SQLite column value with parameterized statements;
- reset `conversations.chat_messages_message_id_seq` through `pg_get_serial_sequence` and `setval`;
- compare columns, counts, primary-key sets and canonical digests before committing;
- rollback and return a nonzero exit code on any mismatch;
- never print row content, DSN, contact details or message text.

- [ ] **Step 4: 运行临时单元测试并确认 GREEN**

Run:

```powershell
python -m pytest C:\tmp\lingjing-postgres-migration-20260722\test_migrate_sqlite_to_postgres.py -q
```

Expected: 2 passed。

- [ ] **Step 5: 运行只读预检**

Run:

```powershell
python C:\tmp\lingjing-postgres-migration-20260722\migrate_sqlite_to_postgres.py --workspace . --source-dir C:\tmp\lingjing-postgres-migration-20260722 --check-only
```

Expected: 报告 conversations `5/100/46 → 0/0/0`、feedback `2 → 0`、景点和美食语义一致，并显示 `SAFE_TO_MIGRATE=true`。

### Task 3: 执行精确补迁并独立验证

**Files:**
- Read outside workspace: `C:/tmp/lingjing-postgres-migration-20260722/*.db`
- Read/Write: PostgreSQL schemas `attractions`、`conversations`、`feedback`、`foods`

**Interfaces:**
- Consumes: Task 1 backups and Task 2 checked migration tool。
- Produces: eight PostgreSQL tables exactly matching SQLite sources。

- [ ] **Step 1: 再次确认没有写入进程和目标漂移**

Run Task 1 Step 1 and Task 2 Step 5 again.

Expected: no writer and `SAFE_TO_MIGRATE=true`。

- [ ] **Step 2: 执行单事务迁移**

Run:

```powershell
python C:\tmp\lingjing-postgres-migration-20260722\migrate_sqlite_to_postgres.py --workspace . --source-dir C:\tmp\lingjing-postgres-migration-20260722 --apply
```

Expected: exit code 0，输出八张表 `COUNT_MATCH=true KEY_MATCH=true HASH_MATCH=true` 和 `TRANSACTION_COMMITTED=true`。

- [ ] **Step 3: 以只读模式独立复核**

Run:

```powershell
python C:\tmp\lingjing-postgres-migration-20260722\migrate_sqlite_to_postgres.py --workspace . --source-dir C:\tmp\lingjing-postgres-migration-20260722 --check-only --require-exact
```

Expected: 八张表的字段、行数、主键和哈希全部一致；会话 5、消息 100、实时轮次 46、反馈 2、景点 8+8、美食 6+6。

- [ ] **Step 4: 验证 PostgreSQL 存储测试**

Run:

```powershell
python -m pytest -q tests/test_conversation_store.py tests/test_attraction_store.py tests/test_food_store.py tests/test_feedback_store.py --basetemp .pytest_tmp_pg_store_20260722
```

Expected: 12 passed。

### Task 4: 强制 PostgreSQL 配置并消除测试对生产凭据的依赖

**Files:**
- Modify: `src/lingjing_ai/config/settings.py`
- Modify: `src/lingjing_ai/api/app.py`
- Modify: `tests/test_settings.py`
- Modify: `tests/conftest.py`
- Modify: database-dependent test modules identified by `rg -l "create_app|ConversationStore|AttractionStore|FoodStore|FeedbackStore" tests -g '*.py'`

**Interfaces:**
- Consumes: `DATABASE_URL` and optional `DATABASE_SCHEMA_PREFIX`。
- Produces: `AppSettings.database_url: str` with empty default and explicit startup validation; `postgres_test_context` fixture based on `TEST_DATABASE_URL` or explicitly supplied `DATABASE_URL`。

- [ ] **Step 1: 写配置失败测试**

Add to `tests/test_settings.py`:

```python
def test_database_url_has_no_hardcoded_default(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = AppSettings.for_workspace(tmp_path)
    assert settings.database_url == ""
```

Add an API construction test that creates settings with `database_url=""` and asserts `create_app` raises `RuntimeError` containing `DATABASE_URL`.

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```powershell
python -m pytest tests/test_settings.py::test_database_url_has_no_hardcoded_default -q
```

Expected: 当前硬编码 AgentDB DSN 导致断言失败。

- [ ] **Step 3: 实现最小配置修复**

Change the dataclass field and loader to:

```python
database_url: str = ""

database_url=(_env_value("DATABASE_URL", workspace_env, "") or "").strip(),
```

Before constructing stores in `create_app`, add:

```python
database_url = pipeline.settings.database_url.strip()
if not database_url:
    raise RuntimeError("DATABASE_URL is required for PostgreSQL storage")
```

- [ ] **Step 4: 重构测试隔离 fixture**

`tests/conftest.py` must remove `DEFAULT_DATABASE_URL` and expose:

```python
@pytest.fixture
def postgres_test_context(monkeypatch: pytest.MonkeyPatch):
    dsn = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    prefix = f"t{uuid.uuid4().hex[:12]}_"
    monkeypatch.setenv("DATABASE_URL", dsn)
    monkeypatch.setenv("DATABASE_SCHEMA_PREFIX", prefix)
    yield {"dsn": dsn, "prefix": prefix}
    for base in _SCHEMA_BASES:
        drop_schema(dsn, f"{prefix}{base}")
```

`pg_dsn` and four schema fixtures must depend on `postgres_test_context`. Database-dependent modules must opt in with `pytestmark = pytest.mark.usefixtures("postgres_test_context")`; pure unit modules must not connect to PostgreSQL.

- [ ] **Step 5: 验证 RED→GREEN 和无数据库单元测试**

Run:

```powershell
$testDatabaseUrl = python -c "import sys; from pathlib import Path; sys.path.insert(0, 'src'); from lingjing_ai.config.settings import AppSettings; print(AppSettings.for_workspace(Path.cwd()).database_url)"
$env:TEST_DATABASE_URL = $testDatabaseUrl
python -m pytest tests/test_settings.py -q
python -m pytest tests/test_answer_formatter.py tests/test_route_summary.py tests/test_transcript_normalizer.py -q
```

Expected: settings tests pass；三个纯单元测试模块在没有创建 PostgreSQL schema 的情况下通过。

- [ ] **Step 6: 提交配置与测试隔离修复**

```powershell
git add -- src/lingjing_ai/config/settings.py src/lingjing_ai/api/app.py tests/conftest.py tests/test_settings.py
git add -- tests/test_admin_analytics.py tests/test_admin_documents.py tests/test_admin_frontend.py tests/test_agent_api.py tests/test_amap_api.py tests/test_api.py tests/test_asr_glossary.py tests/test_attraction_api.py tests/test_attraction_store.py tests/test_conversation_store.py tests/test_feedback_store.py tests/test_food_feedback_api.py tests/test_food_store.py tests/test_frontend.py tests/test_history_sessions_api.py tests/test_langgraph_agent_executor.py tests/test_realtime_api.py tests/test_realtime_conversation.py tests/test_streaming_chat.py
git commit -m "fix: require explicit PostgreSQL configuration"
```

Expected: 只提交列出的 PostgreSQL 配置与测试文件。

### Task 5: 清除 SQLite 运行残留和数据库文件

**Files:**
- Modify: `.gitignore`
- Modify: `.dockerignore`
- Modify: `src/lingjing_ai/realtime/session.py`
- Modify: `src/lingjing_ai/assets/attractions/README.md`
- Delete individually: five `.db` files listed in Global Constraints

**Interfaces:**
- Consumes: Task 3 exact verification success。
- Produces: current workspace with no `.db` file and no runtime SQLite reference。

- [ ] **Step 1: 建立会失败的残留扫描**

Run:

```powershell
rg -n -i "sqlite|sqlite3|\.db\b" src scripts frontend/src tests Dockerfile .dockerignore .gitignore
```

Expected: 至少命中 realtime 注释、attraction README、ignore 规则和 tracked frontend database evidence。

- [ ] **Step 2: 更新运行注释与忽略规则**

Change `src/lingjing_ai/realtime/session.py` from “history as SQLite” to “history persisted in PostgreSQL”. Remove `data/*.db` from `.gitignore`; remove any Docker rule or comment that treats SQLite as an image data source. Update the attraction asset README to describe PostgreSQL seeding and remove file-deletion instructions.

- [ ] **Step 3: 逐个删除明确 SQLite 文件**

Run each command separately only after Task 3 passes:

```powershell
Remove-Item -LiteralPath data\attractions.db
Remove-Item -LiteralPath data\conversations.db
Remove-Item -LiteralPath data\feedback.db
Remove-Item -LiteralPath data\foods.db
Remove-Item -LiteralPath frontend\data\conversations.db
```

Expected: 五个明确文件消失；工作区外备份仍存在。

- [ ] **Step 4: 验证工作区不含 SQLite 数据库**

Run:

```powershell
Get-ChildItem data,frontend\data -File -Filter *.db
```

Expected: no output。

- [ ] **Step 5: 提交运行残留清理**

```powershell
git add -- .gitignore .dockerignore src/lingjing_ai/realtime/session.py src/lingjing_ai/assets/attractions/README.md frontend/data/conversations.db
git commit -m "refactor: retire SQLite storage artifacts"
```

### Task 6: 更新 PostgreSQL 与 Docker 现行文档

**Files:**
- Modify: `project_structure.md`
- Modify: `requirement.md`
- Modify: `docs/conversation_design.md`
- Modify: `docs/qwen_audio_realtime.md`
- Modify: `docs/项目部署运行配置说明书.md`
- Modify: `docs/superpowers/specs/2026-07-20-docker-competition-image-design.md`
- Modify: `Dockerfile`

**Interfaces:**
- Consumes: PostgreSQL-only configuration and Task 5 file state。
- Produces: deployment docs and image behavior that require external PostgreSQL。

- [ ] **Step 1: 扫描现行说明中的 SQLite 内容**

Run:

```powershell
rg -n -i "sqlite|sqlite3|\.db\b" project_structure.md requirement.md docs src/lingjing_ai/assets Dockerfile
```

Expected: output lists every remaining migration-era statement。

- [ ] **Step 2: 逐文档改写为 PostgreSQL**

The updated documents must state all of the following explicitly:

- schemas are `attractions`, `conversations`, `feedback`, and `foods`;
- `DATABASE_URL` is mandatory and secret;
- Docker does not bundle PostgreSQL and container `localhost` is not the host database;
- `data/` persists images, uploaded documents, manifests and analytics snapshots, not relational data;
- PostgreSQL backup uses `pg_dump`, not copying database files;
- application startup initializes missing tables and seeds empty attraction/food schemas;
- conversation and realtime completion history is stored in PostgreSQL.

- [ ] **Step 3: 修正 Docker 镜像语义**

Keep `psycopg[binary]` in `requirements-docker.txt`. Ensure the Dockerfile copies only runtime file assets from `data/`, exposes `DATABASE_URL` as a runtime requirement in documentation, and does not describe `/app/data` or `/app/qdrant_db` as holding SQLite.

- [ ] **Step 4: 验证现行文档无 SQLite 引用**

Run:

```powershell
rg -n -i "sqlite|sqlite3|\.db\b" project_structure.md requirement.md docs/conversation_design.md docs/qwen_audio_realtime.md docs/项目部署运行配置说明书.md src/lingjing_ai/assets Dockerfile .dockerignore .gitignore
git ls-files "*.db"
```

Expected: both commands produce no output。`docs/superpowers/` 下的设计和计划属于迁移审计证据，不属于现行运行说明。

- [ ] **Step 5: 提交文档和 Docker 更新**

```powershell
git add -- project_structure.md requirement.md docs/conversation_design.md docs/qwen_audio_realtime.md docs/项目部署运行配置说明书.md docs/superpowers/specs/2026-07-20-docker-competition-image-design.md Dockerfile requirements-docker.txt
git commit -m "docs: document PostgreSQL-only deployment"
```

### Task 7: 全项目证据化审计与回归验证

**Files:**
- Inspect: `src/`, `scripts/`, `frontend/src/`, `tests/`, `Dockerfile`, dependency manifests and current docs
- Modify only files with a reproducible defect or proven dead reference
- Update: `daily-modify/2026-07-22.md`

**Interfaces:**
- Consumes: PostgreSQL-only codebase。
- Produces: audit findings, verified fixes, test/build evidence and daily change record。

- [ ] **Step 1: 运行全项目静态引用与语法审计**

Run:

```powershell
rg -n -i "sqlite|sqlite3|\.db\b|postgresql://[^\s]+:[^\s]+@|TODO|FIXME|deprecated" src scripts frontend/src tests Dockerfile .dockerignore .gitignore project_structure.md requirement.md docs -g '!docs/superpowers/**'
python -m compileall -q src scripts tests
python -m pip check
```

Expected: SQLite and embedded PostgreSQL password scans return no current-code matches；compileall exit 0。`pip check` 的全局 Anaconda 冲突单独记录，不把无关全局包问题误判为项目缺陷。

- [ ] **Step 2: 运行后端数据库与 API 回归**

Run:

```powershell
$testDatabaseUrl = python -c "import sys; from pathlib import Path; sys.path.insert(0, 'src'); from lingjing_ai.config.settings import AppSettings; print(AppSettings.for_workspace(Path.cwd()).database_url)"
$env:TEST_DATABASE_URL = $testDatabaseUrl
python -m pytest -q tests/test_conversation_store.py tests/test_attraction_store.py tests/test_food_store.py tests/test_feedback_store.py tests/test_history_sessions_api.py tests/test_attraction_api.py tests/test_food_feedback_api.py tests/test_realtime_api.py --basetemp .pytest_tmp_pg_api_20260722
```

Expected: all selected tests pass。

- [ ] **Step 3: 运行完整后端测试**

Run:

```powershell
python -m pytest -q --basetemp .pytest_tmp_full_20260722
```

Expected: 307 collected，0 failed，0 errors；数据库无关单元测试不创建 PostgreSQL schema。

- [ ] **Step 4: 运行前端测试和构建**

Run from `frontend/`:

```powershell
npm test
npm run build
```

Expected: 39 frontend tests pass and Vite build exits 0。若受沙箱父目录权限阻止，使用权限审批重跑同一构建命令，不修改 Vite 配置来规避权限。

- [ ] **Step 5: 构建并检查 Docker 镜像**

Run:

```powershell
docker buildx build --platform linux/amd64 --load -t lingjing-ai:postgres-audit .
docker run --rm lingjing-ai:postgres-audit python -c "from pathlib import Path; files=list(Path('/app').rglob('*.db')); assert not files, files"
docker image inspect lingjing-ai:postgres-audit --format "{{.Os}}/{{.Architecture}}"
```

Expected: build exit 0, image has no `.db`, architecture is `linux/amd64`。Docker Engine unavailable时报告明确外部阻塞，不宣称镜像验证成功。

- [ ] **Step 6: 更新 Daily Modify 记录**

Append one factual session entry to `daily-modify/2026-07-22.md` with every changed file, reason, migration counts, backup directory, exact verification commands and unresolved external blockers. Do not overwrite earlier entries.

- [ ] **Step 7: 最终差异与需求复核**

Run:

```powershell
git status --short
git diff --check
git diff --stat
```

Expected: no whitespace errors；all changes map to this plan or pre-existing user work；no unrelated file is deleted or staged。
