# “灵境智导”品牌名称替换实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将所有当前面向游客、管理员和项目使用者的品牌名称统一为“灵境智导”，同时保持现有技术标识和数据兼容。

**Architecture:** 品牌替换保持在静态展示和人类可读元数据层，不引入新的运行时配置。先用契约测试划定“必须替换的可见文案”和“必须保留的内部标识”，再分游客端、管理端/API、文档与评测三组实施，最后以仓库扫描、测试、构建和浏览器验收收口。

**Tech Stack:** Vue 3、Vite、FastAPI、Python/pytest、Node.js test runner、静态 HTML/Markdown/JSON。

## Global Constraints

- 中文主品牌固定为 `灵境智导`，不新增英文译名。
- 当前界面不再展示 `LingJing AI`、`LINGJING AI` 或 `灵境 AI`。
- `LJ` 图形标记、现有 Logo 图形、颜色和布局保持不变。
- 保留 `lingjing_ai`、`lingjing-ai`、`LingJing_AI`、全部 `lingjing_*`/`lingjing.*` 存储键、Redis 前缀、Neo4j 数据库名和数据文件名。
- 不修改 API 路径、字段、数据库、WebSocket 事件或业务逻辑。
- 不改写 `docs/superpowers/`、`daily-modify/` 中的历史记录。
- 禁止批量删除文件；本计划不需要删除任何文件。

---

### Task 1: 建立品牌可见性与兼容性契约

**Files:**
- Modify: `tests/test_frontend.py`
- Modify: `tests/test_admin_frontend.py`

**Interfaces:**
- Consumes: 现有 `create_app()` 测试工厂和静态源码契约。
- Produces: 新品牌、旧品牌消失及内部标识保留的回归保护。

- [ ] **Step 1: 在游客端测试中写入失败契约**

在 `tests/test_frontend.py` 的游客端品牌相关测试中加入：

```python
app_shell_source = Path("frontend/src/App.vue").read_text(encoding="utf-8")
chat_source = Path("frontend/src/components/ChatMain.vue").read_text(encoding="utf-8")
intro_source = Path(
    "frontend/src/features/scenic-intro/components/ScenicIntro.vue"
).read_text(encoding="utf-8")
index_source = Path("frontend/index.html").read_text(encoding="utf-8")

for source in (app_shell_source, chat_source, intro_source, index_source):
    assert "灵境智导" in source
    assert "LingJing AI" not in source
    assert "LINGJING AI" not in source

assert "给灵境智导发送消息，例如：给我推荐灵山胜境的游玩路线" in chat_source
assert 'title="灵境智导 RAG API"' in Path("src/lingjing_ai/api/app.py").read_text(encoding="utf-8")
assert 'name = "lingjing-ai"' in Path("pyproject.toml").read_text(encoding="utf-8")
assert 'const VISITOR_STORAGE_KEY = "lingjing_visitor_id"' in Path(
    "frontend/src/lib/visitorIdentity.js"
).read_text(encoding="utf-8")
```

- [ ] **Step 2: 在管理端测试中写入失败契约**

将 `tests/test_admin_frontend.py::test_all_admin_pages_share_sidebar_navigation` 的品牌断言改为：

```python
assert "灵境智导" in page.text
assert "LingJing AI" not in page.text
assert "LingJing AI Admin" not in page.text
```

- [ ] **Step 3: 运行测试并确认因旧品牌仍存在而失败**

Run:

```powershell
python -m pytest tests/test_frontend.py tests/test_admin_frontend.py -q
```

Expected: FAIL，失败信息指出游客端或管理端仍包含 `LingJing AI`。

- [ ] **Step 4: 提交测试契约**

```powershell
git add -- tests/test_frontend.py tests/test_admin_frontend.py
git commit -m "test: define Lingjing Zhidao brand contract"
```

---

### Task 2: 替换游客端当前品牌文案

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/components/ChatMain.vue`
- Modify: `frontend/src/features/scenic-intro/components/ScenicIntro.vue`
- Modify: `frontend/index.html`
- Modify: `frontend/visitor.html`

**Interfaces:**
- Consumes: Task 1 的游客端静态契约。
- Produces: 游客端统一显示“灵境智导”，内部会话与身份键不变。

- [ ] **Step 1: 替换共享外壳、导游页和开场品牌**

应用以下精确文案：

```vue
<!-- App.vue -->
<strong>灵境智导</strong>

<!-- ChatMain.vue -->
<p class="brand-mark">灵境智导</p>
<textarea placeholder="给灵境智导发送消息，例如：给我推荐灵山胜境的游玩路线"></textarea>

<!-- ScenicIntro.vue -->
<span>灵境智导 · 灵山胜境</span>
```

- [ ] **Step 2: 替换浏览器标题与旧版回退页面**

将 `frontend/index.html` 的标题改为：

```html
<title>灵境智导游客端</title>
```

将 `frontend/visitor.html` 可见眉题改为：

```html
<p class="eyebrow">灵境智导</p>
```

- [ ] **Step 3: 运行游客端契约并确认该组通过**

Run:

```powershell
python -m pytest tests/test_frontend.py -q
```

Expected: PASS。

- [ ] **Step 4: 提交游客端品牌替换**

```powershell
git add -- frontend/src/App.vue frontend/src/components/ChatMain.vue frontend/src/features/scenic-intro/components/ScenicIntro.vue frontend/index.html frontend/visitor.html
git commit -m "feat: rename visitor brand to Lingjing Zhidao"
```

---

### Task 3: 替换管理端、API 与包描述品牌

**Files:**
- Modify: `frontend/admin_analytics.html`
- Modify: `frontend/admin_attractions.html`
- Modify: `frontend/admin_documents.html`
- Modify: `frontend/admin_foods.html`
- Modify: `frontend/admin_feedback.html`
- Modify: `src/lingjing_ai/api/app.py`
- Modify: `src/lingjing_ai/__init__.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: Task 1 的管理端与兼容性契约。
- Produces: 五个管理页面、OpenAPI 标题、构建提示页和包描述使用新品牌。

- [ ] **Step 1: 统一五个管理页面品牌**

所有管理页面侧栏使用：

```html
<strong>灵境智导</strong>
```

`admin_foods.html` 与 `admin_feedback.html` 顶部眉题使用：

```html
<p class="eyebrow">灵境智导 · 管理中心</p>
```

保持每页 5 个导航项、1 个激活项和 `LJ` 标记不变。

- [ ] **Step 2: 更新 FastAPI 与构建提示页标题**

在 `src/lingjing_ai/api/app.py` 使用：

```python
app = FastAPI(title="灵境智导 RAG API")
```

构建提示 HTML 使用：

```html
<title>灵境智导游客端</title>
```

- [ ] **Step 3: 更新人类可读包描述但保留包名**

`src/lingjing_ai/__init__.py`：

```python
"""灵境智导后端包。"""
```

`pyproject.toml`：

```toml
name = "lingjing-ai"
description = "灵境智导景区 RAG 与智能体后端"
```

- [ ] **Step 4: 运行管理端与游客端契约**

Run:

```powershell
python -m pytest tests/test_admin_frontend.py tests/test_frontend.py -q
```

Expected: PASS，且内部 `lingjing-ai` 契约继续通过。

- [ ] **Step 5: 提交管理端与后端元数据替换**

```powershell
git add -- frontend/admin_analytics.html frontend/admin_attractions.html frontend/admin_documents.html frontend/admin_foods.html frontend/admin_feedback.html src/lingjing_ai/api/app.py src/lingjing_ai/__init__.py pyproject.toml
git commit -m "feat: rename admin and API brand to Lingjing Zhidao"
```

---

### Task 4: 替换当前文档与评测元数据

**Files:**
- Modify: `evaluation/README.md`
- Modify: `evaluation/datasets/lingjing_qa_v1.json`
- Modify: `scripts/build_qa_eval_dataset.py`
- Modify: `scripts/evaluate_qa.py`
- Modify: `src/lingjing_ai/evaluation/reporter.py`
- Modify: `docs/项目部署运行配置说明书.md`
- Modify: `requirement.md`
- Modify: `project_structure.md`

**Interfaces:**
- Consumes: 已确认的品牌规范。
- Produces: 当前说明文档、评测输入、评测输出与重新生成脚本不会恢复旧品牌。

- [ ] **Step 1: 更新评测标题和生成源**

使用以下文案：

```text
灵境智导问答评测
灵境智导全链路问答评测集
灵境智导问答评测报告
Validate and run the 灵境智导 QA evaluation dataset.
```

同时修改现有 JSON 标题和生成脚本中的源标题，文件名 `lingjing_qa_v1.json` 保持不变。

- [ ] **Step 2: 更新当前项目文档的人类可读标题**

使用：

```markdown
# 灵境智导项目部署运行配置说明书
# 灵境智导项目环境要求
```

`project_structure.md` 中项目叙述改用“灵境智导”，但所有 `LingJing_AI` 路径、`lingjing_ai` 导入和命令原样保留。systemd 仅修改：

```ini
Description=灵境智导 FastAPI Service
```

- [ ] **Step 3: 扫描当前文件并确认旧品牌已清除**

Run:

```powershell
rg -n -i "LingJing AI|LINGJING AI|灵境\s+AI" frontend src/lingjing_ai pyproject.toml evaluation scripts docs requirement.md project_structure.md -g "!frontend/node_modules/**" -g "!frontend/dist/**" -g "!frontend/static/vendor/**" -g "!docs/superpowers/**" -g "!daily-modify/**" -g "!*.min.js"
```

Expected: 无输出。内部 `lingjing_ai`、`lingjing-ai` 和 `LingJing_AI` 仍可存在。

- [ ] **Step 4: 提交文档与评测元数据替换**

```powershell
git add -- evaluation/README.md evaluation/datasets/lingjing_qa_v1.json scripts/build_qa_eval_dataset.py scripts/evaluate_qa.py src/lingjing_ai/evaluation/reporter.py docs/项目部署运行配置说明书.md requirement.md project_structure.md
git commit -m "docs: rename project references to Lingjing Zhidao"
```

---

### Task 5: 最终验证与浏览器验收

**Files:**
- Modify: `daily-modify/2026-07-20.md`

**Interfaces:**
- Consumes: Tasks 1–4 的完整实现。
- Produces: 可发布构建、浏览器视觉证据和每日修改记录。

- [ ] **Step 1: 运行前后端测试**

Run:

```powershell
python -m pytest -q
```

Expected: 全部通过，仅允许已有 openpyxl 弃用警告。

Run from `frontend/`:

```powershell
npm test
```

Expected: 全部通过。

- [ ] **Step 2: 运行生产构建**

Run from `frontend/`:

```powershell
npm run build
```

Expected: Vite 构建成功，生成带哈希的新静态资源。

- [ ] **Step 3: 验证内部兼容标识仍存在**

Run:

```powershell
rg -n "lingjing_ai|lingjing-ai|lingjing_visitor_id|lingjing_current_session_id|lingjing_digital_human_avatar|lingjing\.guide\.intro\.seen\.v1" pyproject.toml src frontend/src
```

Expected: 包名、导入路径和存储键均能匹配到原值。

- [ ] **Step 4: 浏览器验收**

在运行中的 `http://127.0.0.1:8000` 检查：

- `/visitor/guide`：侧栏、开场、导游顶栏、输入提示和标签标题。
- `/visitor/explore`、`/visitor/map`、`/visitor/food`、`/visitor/feedback`：共享品牌名称。
- `/admin/analytics`、`/admin/attractions`、`/admin/documents`、`/admin/foods`、`/admin/feedback`：侧栏品牌及管理眉题。
- `/docs`：OpenAPI 页面标题包含“灵境智导 RAG API”。

不得调用真实 AI、实时语音或付费路线服务。

- [ ] **Step 5: 记录每日修改**

向 `daily-modify/2026-07-20.md` 追加本次品牌替换涉及文件、兼容边界、测试和浏览器验收结果，不改写已有条目。

- [ ] **Step 6: 检查最终差异**

Run:

```powershell
git diff --check
git status --short
```

Expected: 无空白错误；仅出现本计划明确修改或仓库已有未跟踪临时目录。
