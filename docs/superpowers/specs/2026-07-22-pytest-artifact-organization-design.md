# Pytest 测试产物目录整理设计

## 目标

把项目根目录现有的 pytest 缓存和临时运行目录集中到 `test-artifacts/pytest/`，保留全部现有内容，并让后续测试默认写入统一位置。

## 方案比较

1. 只移动现有目录：改动最少，但下一次 pytest 仍会在根目录重新生成缓存和临时目录。
2. 移动现有目录并更新 pytest 配置：既整理当前目录，也防止后续再次散落，采用此方案。
3. 删除现有临时目录：最干净，但会丢失诊断产物，且不符合本项目禁止批量删除的约束。

## 目录结构

```text
test-artifacts/
└── pytest/
    ├── cache/
    ├── current/
    └── runs/
        └── <现有运行目录>
```

- `.pytest_cache/` 移动为 `test-artifacts/pytest/cache/`。
- 每个 `.pytest_tmp*` 目录逐个移动到 `test-artifacts/pytest/runs/`，保留原目录名以便追溯。
- pytest 的 `cache_dir` 指向 `test-artifacts/pytest/cache`。
- pytest 的默认 `--basetemp` 指向 `test-artifacts/pytest/current`；该目录只存放可覆盖的当前运行临时内容。
- `.gitignore` 忽略整个 `/test-artifacts/`。

## 安全边界

- 移动前确认没有 Python 或 pytest 进程。
- 每个源路径和目标路径都解析为工作区内绝对路径。
- 不使用通配移动、递归删除或批量删除。
- 每个目录单独执行移动；单项失败时停止处理该项并保留原目录。
- 不移动业务数据、测试源码、报告或工作区外文件。

## 验证

- 项目根目录不再存在 `.pytest_cache` 或 `.pytest_tmp*` 目录。
- 移动前后的目录数量一致。
- `python -m pytest --collect-only -q` 可正常读取新配置。
- 运行一个纯单元测试后，缓存和临时内容只出现在 `test-artifacts/pytest/`。
- `git status --short` 不显示测试产物目录，只显示配置和设计记录改动。
