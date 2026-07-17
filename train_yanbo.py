"""彦博长期训练编排器：新数据、导师蒸馏、断点续训、评估与发布。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from assistant_engine import DEFAULT_ADAPTER_PATH, DISPLAY_NAME
from console_utils import configure_utf8_console


ROUND_STATE = Path("data/training_round_state.json")


def run(command: list[str], required: bool = True) -> int:
    print("\n执行：" + " ".join(command[1:]))
    completed = subprocess.run(command, check=False)
    if required and completed.returncode != 0:
        raise RuntimeError(f"步骤执行失败，退出码：{completed.returncode}")
    return completed.returncode


def load_round_state() -> dict:
    if not ROUND_STATE.exists():
        return {"completed_round": 0, "history": []}
    try:
        return json.loads(ROUND_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {"completed_round": 0, "history": []}


def current_training_step() -> int:
    state_path = DEFAULT_ADAPTER_PATH / "training_state.json"
    if not state_path.exists():
        return 0
    try:
        return int(json.loads(state_path.read_text(encoding="utf-8")).get("step", 0))
    except (OSError, ValueError, TypeError):
        return 0


def save_round_state(state: dict) -> None:
    ROUND_STATE.parent.mkdir(parents=True, exist_ok=True)
    ROUND_STATE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description=f"长期训练{DISPLAY_NAME}")
    parser.add_argument("--steps", type=int, default=80, help="本轮新增优化步数")
    parser.add_argument("--teacher-count", type=int, default=8, help="本轮导师样本数量")
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--max-length", type=int, default=320)
    parser.add_argument("--skip-teacher", action="store_true")
    parser.add_argument("--skip-eval", action="store_true")
    args = parser.parse_args()
    if args.steps <= 0 or args.teacher_count < 0 or args.max_length < 128:
        raise ValueError("训练参数无效")

    state = load_round_state()
    round_number = int(state.get("completed_round", 0)) + 1
    before_step = current_training_step()

    print(f"{DISPLAY_NAME}长期训练第{round_number}轮")
    print(f"当前累计训练步数：{before_step}")
    print(f"本轮计划新增：{args.steps}步")
    print(f"训练序列长度：{args.max_length}")

    teacher_status = "跳过"
    if not args.skip_teacher and args.teacher_count > 0:
        code = run(
            [
                sys.executable,
                "generate_teacher_data.py",
                "--round",
                str(round_number),
                "--count",
                str(args.teacher_count),
            ],
            required=False,
        )
        teacher_status = "完成" if code == 0 else "不可用，已继续使用规则数据"

    run([
        sys.executable,
        "build_advanced_dataset.py",
        "--round",
        str(round_number),
    ])

    run([
        sys.executable,
        "continue_training.py",
        "--steps",
        str(args.steps),
        "--learning-rate",
        str(args.learning_rate),
        "--max-length",
        str(args.max_length),
        "--save-every",
        str(max(10, min(20, args.steps))),
    ])

    evaluation_status = "跳过"
    if not args.skip_eval:
        ability_code = run(
            [sys.executable, "evaluate.py", "--mode", "fallback", "--advanced-only"],
            required=False,
        )
        image_code = run(
            [sys.executable, "evaluate_multimodal.py", "--mode", "auto"],
            required=False,
        )
        ability_status = "通过" if ability_code == 0 else "未通过"
        image_status = "通过" if image_code == 0 else "未通过"
        evaluation_status = f"文字能力{ability_status}，图片能力{image_status}"

    release_code = run([sys.executable, "release_model.py"], required=False)
    release_status = "完成" if release_code == 0 else "训练参数已保存，发布配置刷新失败"

    after_step = current_training_step()
    history = list(state.get("history", []))
    history.append({
        "round": round_number,
        "started_step": before_step,
        "finished_step": after_step,
        "requested_steps": args.steps,
        "teacher_status": teacher_status,
        "evaluation_status": evaluation_status,
        "release_status": release_status,
        "completed_at": datetime.now().isoformat(timespec="seconds"),
    })
    state["current_version"] = DISPLAY_NAME
    state["completed_round"] = round_number
    state["total_training_steps"] = after_step
    state["history"] = history[-50:]
    save_round_state(state)

    print("\n长期训练轮次完成")
    print(f"轮次：{round_number}")
    print(f"累计训练步数：{after_step}")
    print(f"导师数据：{teacher_status}")
    print(f"自动评估：{evaluation_status}")
    print(f"发布配置：{release_status}")
    print("下次再次运行01_train.bat会进入下一轮，并继续读取当前训练断点。")


if __name__ == "__main__":
    main()
