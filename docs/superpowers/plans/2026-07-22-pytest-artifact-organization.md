# Pytest Artifact Organization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把根目录的 pytest 缓存和临时运行目录集中到 `test-artifacts/pytest/`，并让后续 pytest 默认使用该位置。

**Architecture:** 历史缓存单独移动到 `cache/`，历史临时运行目录逐个移动到 `runs/`，当前测试使用可覆盖的 `current/`。pytest 配置负责后续路径，Git 忽略整个测试产物根目录。

**Tech Stack:** PowerShell、pytest 7、TOML、Git

## Global Constraints

- 不删除任何文件或目录。
- 不使用通配移动或递归移动命令。
- 每个源目录和目标目录必须解析到工作区 `C:\Users\86181\Desktop\Python\LingJing_AI` 内。
- 每个现有测试目录单独执行 `Move-Item -LiteralPath`。
- 保留用户现有未提交改动，不暂存无关文件。

---

### Task 1: 集中现有 pytest 产物并配置后续路径

**Files:**
- Modify: `.gitignore`
- Modify: `pyproject.toml`
- Create at runtime: `test-artifacts/pytest/cache/`
- Create at runtime: `test-artifacts/pytest/current/`
- Create at runtime: `test-artifacts/pytest/runs/`

**Interfaces:**
- Consumes: 根目录中精确枚举出的 `.pytest_cache` 和 `.pytest_tmp*` 目录。
- Produces: pytest `cache_dir=test-artifacts/pytest/cache` 和默认 `--basetemp=test-artifacts/pytest/current`。

- [ ] **Step 1: 验证没有活动测试进程并记录源目录**

运行：

```powershell
Get-Process | Where-Object { $_.ProcessName -match 'pytest|python' }
Get-ChildItem -LiteralPath . -Directory -Force | Where-Object { $_.Name -like '.pytest*' }
```

预期：没有 Python/pytest 进程；源目录数量为 22。

- [ ] **Step 2: 创建工作区内目标目录并验证解析路径**

运行三个独立命令：

```powershell
New-Item -ItemType Directory -Path test-artifacts\pytest\runs -Force
New-Item -ItemType Directory -Path test-artifacts\pytest\current -Force
Resolve-Path test-artifacts\pytest\runs
```

预期：解析路径以项目根目录开头。

- [ ] **Step 3: 逐个移动缓存和临时目录**

缓存使用：

```powershell
Move-Item -LiteralPath .pytest_cache -Destination test-artifacts\pytest\cache
```

其余 21 个 `.pytest_tmp*` 目录分别使用一个明确命令：

```powershell
Move-Item -LiteralPath .pytest_tmp -Destination test-artifacts\pytest\runs\.pytest_tmp
Move-Item -LiteralPath .pytest_tmp_audit_20260722_0945 -Destination test-artifacts\pytest\runs\.pytest_tmp_audit_20260722_0945
Move-Item -LiteralPath .pytest_tmp_audit_settings_20260722_0945 -Destination test-artifacts\pytest\runs\.pytest_tmp_audit_settings_20260722_0945
Move-Item -LiteralPath .pytest_tmp_full_pg_diagnose_20260722 -Destination test-artifacts\pytest\runs\.pytest_tmp_full_pg_diagnose_20260722
Move-Item -LiteralPath .pytest_tmp_full_pg_final_20260722 -Destination test-artifacts\pytest\runs\.pytest_tmp_full_pg_final_20260722
Move-Item -LiteralPath .pytest_tmp_history_diagnosis_20260718 -Destination test-artifacts\pytest\runs\.pytest_tmp_history_diagnosis_20260718
Move-Item -LiteralPath .pytest_tmp_pg_config_green_20260722 -Destination test-artifacts\pytest\runs\.pytest_tmp_pg_config_green_20260722
Move-Item -LiteralPath .pytest_tmp_pg_config_red_20260722 -Destination test-artifacts\pytest\runs\.pytest_tmp_pg_config_red_20260722
Move-Item -LiteralPath .pytest_tmp_pg_integration_final_20260722 -Destination test-artifacts\pytest\runs\.pytest_tmp_pg_integration_final_20260722
Move-Item -LiteralPath .pytest_tmp_pg_stores_final_20260722 -Destination test-artifacts\pytest\runs\.pytest_tmp_pg_stores_final_20260722
Move-Item -LiteralPath .pytest_tmp_pg_store_20260722 -Destination test-artifacts\pytest\runs\.pytest_tmp_pg_store_20260722
Move-Item -LiteralPath .pytest_tmp_pg_store_isolated_20260722 -Destination test-artifacts\pytest\runs\.pytest_tmp_pg_store_isolated_20260722
Move-Item -LiteralPath .pytest_tmp_pg_unit_20260722 -Destination test-artifacts\pytest\runs\.pytest_tmp_pg_unit_20260722
Move-Item -LiteralPath .pytest_tmp_pure_final_20260722 -Destination test-artifacts\pytest\runs\.pytest_tmp_pure_final_20260722
Move-Item -LiteralPath .pytest_tmp_qa_opt_20260716_0920 -Destination test-artifacts\pytest\runs\.pytest_tmp_qa_opt_20260716_0920
Move-Item -LiteralPath .pytest_tmp_qa_opt_green2_20260716_1230 -Destination test-artifacts\pytest\runs\.pytest_tmp_qa_opt_green2_20260716_1230
Move-Item -LiteralPath .pytest_tmp_qa_opt_green3_20260716_1245 -Destination test-artifacts\pytest\runs\.pytest_tmp_qa_opt_green3_20260716_1245
Move-Item -LiteralPath .pytest_tmp_qa_opt_green_20260716_1215 -Destination test-artifacts\pytest\runs\.pytest_tmp_qa_opt_green_20260716_1215
Move-Item -LiteralPath .pytest_tmp_qa_opt_red2_20260716_1220 -Destination test-artifacts\pytest\runs\.pytest_tmp_qa_opt_red2_20260716_1220
Move-Item -LiteralPath .pytest_tmp_qa_opt_red3_20260716_1240 -Destination test-artifacts\pytest\runs\.pytest_tmp_qa_opt_red3_20260716_1240
Move-Item -LiteralPath .pytest_tmp_qa_opt_red_20260716_1205 -Destination test-artifacts\pytest\runs\.pytest_tmp_qa_opt_red_20260716_1205
```

预期：每次只移动一个已核验目录；失败项保留原位并单独报告。

- [ ] **Step 4: 配置 pytest 和 Git 忽略规则**

在 `pyproject.toml` 的 `[tool.pytest.ini_options]` 中设置：

```toml
addopts = "--basetemp=test-artifacts/pytest/current"
cache_dir = "test-artifacts/pytest/cache"
```

在 `.gitignore` 中加入：

```gitignore
/test-artifacts/
```

- [ ] **Step 5: 验证目录、配置和测试行为**

运行：

```powershell
python -m pytest --collect-only -q
python -m pytest tests/test_settings.py::test_database_url_has_no_hardcoded_default -q
```

预期：收集 310 项；单元测试通过；根目录 `.pytest*` 目录数量为 0；`test-artifacts/pytest/` 下存在 `cache`、`current`、`runs`。

- [ ] **Step 6: 记录并提交配置变更**

只暂存：

```powershell
git add -- .gitignore pyproject.toml daily-modify/2026-07-22.md docs/superpowers/plans/2026-07-22-pytest-artifact-organization.md
git commit -m "chore: organize pytest artifacts"
```
