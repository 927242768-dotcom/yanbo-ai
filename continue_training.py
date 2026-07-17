"""每次在彦博当前版本的现有微调步数基础上继续训练。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from assistant_engine import DEFAULT_ADAPTER_PATH, DISPLAY_NAME
from console_utils import configure_utf8_console


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description=f"继续训练{DISPLAY_NAME}兼容模式")
    parser.add_argument("--steps", type=int, default=20, help="本次新增优化步数")
    parser.add_argument("--save-every", type=int, default=10)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--max-length", type=int, default=320, help="训练序列最大长度")
    parser.add_argument("--adapter", type=Path, default=DEFAULT_ADAPTER_PATH)
    args = parser.parse_args()

    if args.steps <= 0:
        raise ValueError("--steps 必须大于 0")

    state_path = args.adapter / "training_state.json"
    current_step = 0
    if state_path.exists():
        current_step = int(json.loads(state_path.read_text(encoding="utf-8")).get("step", 0))
    target_step = current_step + args.steps

    print(f"{DISPLAY_NAME}当前训练步数：{current_step}")
    print(f"本次新增：{args.steps} 步，目标：{target_step} 步")
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
    ]
    if current_step > 0:
        command.append("--resume")
    completed = subprocess.run(command, check=False)
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
