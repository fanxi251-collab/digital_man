from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lingjing_ai.evaluation.loader import load_dataset
from lingjing_ai.evaluation.reporter import build_report, write_report
from lingjing_ai.evaluation.runner import run_evaluation
from lingjing_ai.evaluation.validator import validate_dataset


DEFAULT_DATASET = PROJECT_ROOT / "evaluation" / "datasets" / "lingjing_qa_v1.json"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "reports" / "qa_eval"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and run the 灵境智导 QA evaluation dataset.")
    parser.add_argument("--mode", choices=("validate", "offline", "benchmark", "smoke"), default="validate")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--case-id", action="append", default=[], help="Only run the specified case; repeatable.")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--judge-llm", action="store_true")
    parser.add_argument("--judge-model", default="")
    args = parser.parse_args()

    dataset = load_dataset(args.dataset)
    errors = validate_dataset(dataset)
    if errors:
        print("评测集校验失败：")
        for error in errors:
            print(f"- {error}")
        return 1
    if args.mode == "validate":
        print(f"评测集校验通过：{len(dataset.cases)}题，版本 {dataset.dataset_version}")
        return 0

    cases = dataset.cases
    if args.mode == "smoke":
        cases = [case for case in cases if "online-smoke" in case.tags]
    if args.case_id:
        requested = set(args.case_id)
        cases = [case for case in cases if case.case_id in requested]
        missing = requested - {case.case_id for case in cases}
        if missing:
            print("未找到用例：" + "、".join(sorted(missing)))
            return 1
    if args.limit > 0:
        cases = cases[: args.limit]

    scores, runtime = run_evaluation(
        dataset,
        mode=args.mode,
        workspace_dir=PROJECT_ROOT,
        cases=cases,
        judge_llm=args.judge_llm,
        judge_model=args.judge_model,
    )
    report = build_report(dataset, scores, mode=args.mode, runtime=runtime)
    json_path, markdown_path = write_report(
        report,
        args.output_dir,
        create_baseline=args.mode == "benchmark",
    )
    summary = report["summary"]
    print(
        f"评测完成：{len(scores)}题，总分 {summary['deterministic_score']}，"
        f"通过 {summary['passed_cases']}，失败 {summary['failed_cases']}。"
    )
    print(f"JSON报告：{json_path}")
    print(f"Markdown报告：{markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
