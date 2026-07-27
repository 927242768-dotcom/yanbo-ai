"""从第5轮课程中构建失败簇专项数据，同时保留旧能力回放。"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from console_utils import configure_utf8_console


FOCUS_PREFIXES = (
    "round5_grounding_",
    "round5_math_ratio_three",
    "round5_electronics_series",
    "round5_git_safe_revert",
    "round5_instruction_exact_items",
    "round5_instruction_json",
)


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for item in rows:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="构建第5轮失败簇专项训练集")
    parser.add_argument("--source", type=Path, default=Path("data/round5_curriculum_train.jsonl"))
    parser.add_argument("--validation", type=Path, default=Path("data/round5_curriculum_val.jsonl"))
    parser.add_argument("--train-output", type=Path, default=Path("data/round5_failure_focus_train.jsonl"))
    parser.add_argument("--val-output", type=Path, default=Path("data/round5_failure_focus_val.jsonl"))
    parser.add_argument("--replay", type=int, default=700)
    parser.add_argument("--seed", type=int, default=20260726)
    args = parser.parse_args()
    if args.replay < 0:
        raise ValueError("--replay不能小于0")

    rng = random.Random(args.seed)
    rows = load_jsonl(args.source)
    focus = [item for item in rows if str(item.get("category", "")).startswith(FOCUS_PREFIXES)]
    replay_pool = [item for item in rows if item not in focus]
    rng.shuffle(replay_pool)
    replay = replay_pool[: min(args.replay, len(replay_pool))]

    combined = focus + replay
    rng.shuffle(combined)
    validation = load_jsonl(args.validation)

    write_jsonl(args.train_output, combined)
    write_jsonl(args.val_output, validation)
    print(f"失败簇专项训练集：{len(combined)}条，其中专项{len(focus)}条，回放{len(replay)}条")
    print(f"失败簇验证集：{len(validation)}条")


if __name__ == "__main__":
    main()
