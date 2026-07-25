"""在现有彦博-v3适配器基础上继续训练，并支持候选目录隔离。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from assistant_engine import DEFAULT_ADAPTER_PATH, DISPLAY_NAME
from console_utils import configure_utf8_console


def read_step(adapter: Path) -> int:
    state_path = adapter / "training_state.json"
    if not state_path.exists():
        return 0
    try:
        return int(json.loads(state_path.read_text(encoding="utf-8")).get("step", 0))
    except (OSError, TypeError, ValueError):
        return 0


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description=f"继续训练{DISPLAY_NAME}兼容模式")
    parser.add_argument("--steps", type=int, default=20, help="本次计划新增优化步数")
    parser.add_argument("--save-every", type=int, default=10)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--max-length", type=int, default=384, help="训练序列最大长度")
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--val-batches", type=int, default=40)
    parser.add_argument("--early-stopping-patience", type=int, default=6)
    parser.add_argument("--adapter", type=Path, default=DEFAULT_ADAPTER_PATH)
    parser.add_argument(
        "--output",
        type=Path,
        help="候选适配器输出目录；默认直接写回--adapter",
    )
    args = parser.parse_args()

    if args.steps <= 0:
        raise ValueError("--steps必须大于0")

    output = args.output or args.adapter
    output_step = read_step(output)
    source_step = read_step(args.adapter)
    if (output / "adapter_config.json").exists():
        current_step = output_step
        resume = True
        init_adapter: Path | None = None
    else:
        current_step = source_step
        resume = False
        init_adapter = args.adapter
    target_step = current_step + args.steps

    print(f"{DISPLAY_NAME}当前训练步数：{current_step}")
    print(f"本次计划新增：{args.steps}步，目标上限：{target_step}步")
    print(f"训练输出：{output}")
    command = [
        sys.executable,
        "fine_tune_lora.py",
        "--max-steps",
        str(target_step),
        "--save-every",
        str(args.save_every),
        "--learning-rate",
        str(args.learning_rate),
        "--max-length",
        str(args.max_length),
        "--grad-accum",
        str(args.grad_accum),
        "--val-batches",
        str(args.val_batches),
        "--early-stopping-patience",
        str(args.early_stopping_patience),
        "--output",
        str(output),
    ]
    if resume:
        command.append("--resume")
    elif init_adapter is not None:
        command.extend(["--init-adapter", str(init_adapter)])

    completed = subprocess.run(command, check=False)
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
