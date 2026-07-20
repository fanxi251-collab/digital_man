from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from statistics import mean
from typing import Any

from lingjing_ai.evaluation.models import CaseScore, EvaluationCase, EvaluationDataset


SENSITIVE_PATTERN = re.compile(
    r"(?i)(api[_-]?key|authorization|redis_url|password|visitor_id|user_nickname|tourist_id)"
    r"\s*[:=]\s*[^\s,}\]]+"
)


def build_report(
    dataset: EvaluationDataset,
    scores: list[CaseScore],
    *,
    mode: str,
    runtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    case_by_id = {case.case_id: case for case in dataset.cases}
    overall = round(mean(item.deterministic_score for item in scores), 2) if scores else 0.0
    freshness_values = [item.freshness_score for item in scores if item.freshness_score is not None]
    groundedness_values = [item.groundedness_score for item in scores]
    scenic_scores = [
        item
        for item in scores
        if case_by_id[item.case_id].category in {"factual", "explanation", "robustness"}
    ]
    scenic_pass_rate = (
        round(100.0 * sum(item.passed for item in scenic_scores) / len(scenic_scores), 2)
        if scenic_scores
        else None
    )
    report = {
        "report_version": "qa_eval_report_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "dataset": {
            "schema_version": dataset.schema_version,
            "dataset_version": dataset.dataset_version,
            "case_count": len(scores),
            "knowledge_documents": dataset.metadata.get("knowledge_documents", []),
        },
        "runtime": runtime or {},
        "summary": {
            "deterministic_score": overall,
            "groundedness_score": round(mean(groundedness_values), 2) if groundedness_values else 0.0,
            "freshness_score": round(mean(freshness_values), 2) if freshness_values else None,
            "passed_cases": sum(item.passed for item in scores),
            "failed_cases": sum(not item.passed for item in scores),
            "critical_failures": sum(item.critical_failure for item in scores),
            "scenic_factual_accuracy": scenic_pass_rate,
            "scenic_factual_case_count": len(scenic_scores),
            "retrieval_hit_rate": _metric_rate(scores, "retrieval_hit"),
            "answerability_accuracy": _metric_rate(scores, "answerability_correct"),
            "tool_accuracy": _metric_rate(scores, "tool_correct"),
            "first_token_ms_p50": _percentile(_latencies(scores, "first_token_ms"), 50),
            "first_token_ms_p95": _percentile(_latencies(scores, "first_token_ms"), 95),
            "total_ms_p50": _percentile(_latencies(scores, "total_ms"), 50),
            "total_ms_p95": _percentile(_latencies(scores, "total_ms"), 95),
            "scoring_policy": "contest_soft_v1",
            "pass_threshold": 60.0,
        },
        "groups": {
            "destination": _group_scores(scores, case_by_id, "destination"),
            "category": _group_scores(scores, case_by_id, "category"),
            "difficulty": _group_scores(scores, case_by_id, "difficulty"),
            "interaction": _group_scores(scores, case_by_id, "interaction"),
        },
        "conflicts": [
            {
                "case_id": case.case_id,
                "question": case.question,
                "official_source_refs": case.truth.get("official_source_refs", []),
            }
            for case in dataset.cases
            if case.case_id in {item.case_id for item in scores}
            and case.truth.get("freshness_status") == "conflict"
        ],
        "failures": [
            {
                "case_id": item.case_id,
                "question": case_by_id[item.case_id].question,
                "failures": item.failures,
                "actual_answer": item.response.get("answer", ""),
                "reference_answer": item.response.get("reference_answer", ""),
                "sources": item.response.get("sources", []),
                "tool_trace": item.response.get("tool_trace", []),
            }
            for item in scores
            if not item.passed
        ],
        "cases": [item.to_dict() for item in scores],
    }
    return _sanitize(report)


def write_report(report: dict[str, Any], output_dir: Path | str, *, create_baseline: bool = False) -> tuple[Path, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"qa_eval_{report.get('mode', 'unknown')}_{timestamp}"
    json_path = directory / f"{stem}.json"
    markdown_path = directory / f"{stem}.md"
    _atomic_write(json_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(markdown_path, render_markdown(report))
    if create_baseline:
        baseline = directory / "baseline.json"
        if not baseline.exists():
            _atomic_write(baseline, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return json_path, markdown_path


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# 灵境智导问答评测报告",
        "",
        f"- 模式：`{report['mode']}`",
        f"- 数据集版本：`{report['dataset']['dataset_version']}`",
        f"- 用例数：{report['dataset']['case_count']}",
        f"- 确定性总分：{summary['deterministic_score']}",
        f"- 资料忠实度：{summary['groundedness_score']}",
        f"- 信息新鲜度：{summary['freshness_score'] if summary['freshness_score'] is not None else '不适用/待核验'}",
        f"- 通过/失败/关键失败：{summary['passed_cases']}/{summary['failed_cases']}/{summary['critical_failures']}",
        f"- 景区事实问答准确率：{summary.get('scenic_factual_accuracy')}%（{summary.get('scenic_factual_case_count')}题，竞赛口径）",
        f"- 评分策略：{summary.get('scoring_policy', 'default')}，通过阈值：{summary.get('pass_threshold', 70)}",
        "",
        "## 分类表现",
        "",
        "| 分类 | 用例数 | 平均分 | 通过率 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name, item in report["groups"]["category"].items():
        lines.append(f"| {name} | {item['count']} | {item['score']} | {item['pass_rate']}% |")
    lines.extend(["", "## 失败用例", ""])
    if not report["failures"]:
        lines.append("无失败用例。")
    for failure in report["failures"]:
        lines.extend(
            [
                f"### {failure['case_id']}",
                "",
                f"- 问题：{failure['question']}",
                f"- 原因：{'；'.join(failure['failures'])}",
                f"- 实际答案：{failure['actual_answer']}",
                f"- 参考答案：{failure['reference_answer']}",
                "",
            ]
        )
    if report["conflicts"]:
        lines.extend(["## 本地资料与官方信息冲突", ""])
        for item in report["conflicts"]:
            lines.append(f"- `{item['case_id']}` {item['question']}")
    return "\n".join(lines).rstrip() + "\n"


def _group_scores(scores: list[CaseScore], cases: dict[str, EvaluationCase], attribute: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[CaseScore]] = defaultdict(list)
    for score in scores:
        groups[str(getattr(cases[score.case_id], attribute))].append(score)
    return {
        key: {
            "count": len(items),
            "score": round(mean(item.deterministic_score for item in items), 2),
            "pass_rate": round(sum(item.passed for item in items) * 100 / len(items), 2),
        }
        for key, items in sorted(groups.items())
    }


def _metric_rate(scores: list[CaseScore], key: str) -> float | None:
    values = [item.metrics.get(key) for item in scores if item.metrics.get(key) is not None]
    if not values:
        return None
    return round(sum(bool(value) for value in values) * 100 / len(values), 2)


def _latencies(scores: list[CaseScore], key: str) -> list[float]:
    return [float(item.metrics[key]) for item in scores if item.metrics.get(key) is not None]


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile / 100
    lower = int(index)
    upper = min(len(ordered) - 1, lower + 1)
    result = ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)
    return round(result, 2)


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize(item) for key, item in value.items() if key.lower() not in {"api_key", "redis_url", "password", "visitor_id", "user_nickname", "tourist_id"}}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return SENSITIVE_PATTERN.sub(r"\1=<redacted>", value)
    return value


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
