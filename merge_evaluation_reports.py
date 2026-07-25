"""合并同一适配器的分片评测报告，并检查题目索引是否重复或缺失。"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from console_utils import configure_utf8_console


def load_report(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("results"), list):
        raise ValueError(f"无效评测报告：{path}")
    return value


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="合并彦博分片评测报告")
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument(
        "--revalidate",
        action="store_true",
        help="使用当前评测套件的验证器重新检查已保存答案，适用于修正过窄验证规则后重算",
    )
    args = parser.parse_args()

    reports = [load_report(path) for path in args.reports]
    adapters = {str(report.get("adapter", "")) for report in reports}
    executions = {str(report.get("execution", "")) for report in reports}
    suite_totals = {int(report.get("suite_total", 0) or 0) for report in reports}
    if len(adapters) != 1 or len(executions) != 1 or len(suite_totals) != 1:
        raise ValueError("只能合并同一适配器、执行模式和评测套件的报告")

    by_index: dict[int, dict[str, Any]] = {}
    for report in reports:
        for result in report["results"]:
            index = int(result["index"])
            if index in by_index:
                raise ValueError(f"题目索引重复：{index}")
            by_index[index] = result

    suite_total = next(iter(suite_totals))
    missing = [index for index in range(suite_total) if index not in by_index]
    if args.require_complete and missing:
        raise ValueError(f"评测分片不完整，缺少索引：{missing}")

    results = [by_index[index] for index in sorted(by_index)]
    if args.revalidate:
        from evaluate_round4_generalization import CASES

        if suite_total != len(CASES):
            raise ValueError(
                f"当前评测套件共{len(CASES)}题，与报告中的suite_total={suite_total}不一致"
            )
        for result in results:
            index = int(result["index"])
            answer = str(result.get("answer", ""))
            result["passed"] = bool(answer.strip()) and CASES[index].validator(answer)

    passed = sum(bool(result.get("passed")) for result in results)
    categories: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for result in results:
        bucket = categories[str(result.get("category", "general"))]
        bucket[0] += int(bool(result.get("passed")))
        bucket[1] += 1

    merged = {
        "adapter": next(iter(adapters)),
        "execution": next(iter(executions)),
        "suite_total": suite_total,
        "evaluated": len(results),
        "missing_indices": missing,
        "passed": passed,
        "total": len(results),
        "score": round(passed / max(1, len(results)), 4),
        "revalidated": bool(args.revalidate),
        "categories": {
            name: {"passed": values[0], "total": values[1]}
            for name, values in sorted(categories.items())
        },
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"已合并{len(reports)}个分片：{passed}/{len(results)}，得分{merged['score']:.1%}")
    if missing:
        print(f"缺少题目索引：{missing}")


if __name__ == "__main__":
    main()
