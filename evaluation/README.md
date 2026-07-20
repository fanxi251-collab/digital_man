# 灵境智导问答评测

评测集包含120个版本化用例，覆盖事实问答、景点解释、路线建议、地图工具、多轮对话、拒答安全和鲁棒性。

默认采用竞赛口径宽松评分（`contest_soft_v1`）：景区事实问答以“基本答对”为主，拒答识别支持自然语言边界表达，动态票价/场次不因本地资料回答而一票否决，通过阈值为 60 分。报告中的 `scenic_factual_accuracy` 对标赛题“景区问题事实性问答准确率”。

## 常用命令

在项目根目录执行：

```powershell
python scripts\evaluate_qa.py --mode validate
python scripts\evaluate_qa.py --mode offline
python scripts\evaluate_qa.py --mode benchmark
python scripts\evaluate_qa.py --mode benchmark --judge-llm
python scripts\evaluate_qa.py --mode smoke
python scripts\rescore_qa_report.py reports\qa_eval\qa_eval_benchmark_XXXX.json
```

- `validate` 只检查题库结构、证据和固定分布。
- `offline` 使用题库内固定答案和高德回放，完全离线验证评分及报告。
- `benchmark` 使用当前千问、Embedding、Qdrant；高德数据固定回放。完整 120 题会调用模型，耗时较长。
- `smoke` 只执行 8 个 `online-smoke` 用例，并调用真实千问及高德接口。
- `rescore_qa_report.py` 对已有报告换规则重打分，不重新调用模型。

可通过 `--case-id` 重复指定用例，或用 `--limit` 限制数量。`benchmark` 和 `smoke` 需要 `LJAPI_KEY`，`smoke` 还需要 `MAP_API`。

报告默认写入 `reports/qa_eval/`，该目录不会提交 Git。

## 双重事实口径

`groundedness_score` 衡量答案是否符合本地知识资料；`freshness_score` 仅作参考，不决定是否通过。票价、开放时间等动态题允许依据本地资料作答，并鼓励提示以官方/现场信息为准。

修改题目定义后，使用下面的命令重新生成 JSON 并立即校验：

```powershell
python scripts\build_qa_eval_dataset.py
python scripts\evaluate_qa.py --mode validate
```
