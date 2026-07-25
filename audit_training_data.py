"""审计彦博-v3训练数据的重复、泄漏、格式完整性与类别分布。"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from console_utils import configure_utf8_console
from training_quality import is_training_answer_usable


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{path}:{line_number} 不是合法JSON") from exc
        if not isinstance(item, dict):
            raise ValueError(f"{path}:{line_number} 顶层必须是对象")
        rows.append(item)
    return rows


def extract_pair(item: dict[str, Any]) -> tuple[str, str]:
    user = ""
    assistant = ""
    messages = item.get("messages", [])
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role", ""))
            content = str(message.get("content", ""))
            if role == "user":
                user = content
            elif role == "assistant":
                assistant = content
    return user.strip(), assistant.strip()


def normalize_text(text: str) -> str:
    text = text.casefold()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，。！？、；：,.!?;:'\"`~（）()\[\]{}<>《》]", "", text)
    return text


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = [extract_pair(item) for item in rows]
    pair_keys = [(normalize_text(user), normalize_text(answer)) for user, answer in pairs]
    prompt_keys = [normalize_text(user) for user, _ in pairs]
    categories = Counter(str(item.get("category", "general")) for item in rows)
    empty = [index + 1 for index, (user, answer) in enumerate(pairs) if not user or not answer]
    unusable = [
        index + 1
        for index, (_, answer) in enumerate(pairs)
        if answer and not is_training_answer_usable(answer)
    ]
    code_fence_errors = [
        index + 1
        for index, (_, answer) in enumerate(pairs)
        if answer.count("```") % 2 != 0
    ]
    lengths = sorted(len(answer) for _, answer in pairs)
    percentile_95 = lengths[int(0.95 * (len(lengths) - 1))] if lengths else 0
    return {
        "rows": len(rows),
        "unique_pairs": len(set(pair_keys)),
        "duplicate_pairs": len(rows) - len(set(pair_keys)),
        "unique_prompts": len(set(prompt_keys)),
        "duplicate_prompts": len(rows) - len(set(prompt_keys)),
        "empty_rows": empty,
        "unusable_answers": unusable,
        "unbalanced_code_fences": code_fence_errors,
        "assistant_length": {
            "min": lengths[0] if lengths else 0,
            "p50": lengths[len(lengths) // 2] if lengths else 0,
            "p95": percentile_95,
            "max": lengths[-1] if lengths else 0,
        },
        "categories": dict(sorted(categories.items())),
        "prompt_keys": prompt_keys,
        "pair_keys": pair_keys,
    }


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="审计训练集和验证集质量")
    parser.add_argument("--train", type=Path, default=Path("data/quality_sft_train.jsonl"))
    parser.add_argument("--val", type=Path, default=Path("data/quality_sft_val.jsonl"))
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    train_rows = load_rows(args.train)
    val_rows = load_rows(args.val)
    train = summarize(train_rows)
    val = summarize(val_rows)
    prompt_leakage = sorted(set(train.pop("prompt_keys")) & set(val.pop("prompt_keys")))
    pair_leakage = sorted(set(train.pop("pair_keys")) & set(val.pop("pair_keys")))

    report = {
        "train": train,
        "validation": val,
        "cross_split": {
            "prompt_leakage_count": len(prompt_leakage),
            "pair_leakage_count": len(pair_leakage),
            "prompt_leakage_examples": prompt_leakage[:10],
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    critical = (
        train["duplicate_pairs"] > 0
        or val["duplicate_pairs"] > 0
        or bool(train["empty_rows"])
        or bool(val["empty_rows"])
        or bool(train["unusable_answers"])
        or bool(val["unusable_answers"])
        or len(pair_leakage) > 0
    )
    raise SystemExit(1 if critical else 0)


if __name__ == "__main__":
    main()
