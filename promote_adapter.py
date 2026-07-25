"""将通过评测的候选LoRA安全提升为彦博-v3正式兼容适配器。"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

from assistant_engine import DEFAULT_ADAPTER_PATH
from console_utils import configure_utf8_console


REQUIRED_FILES = ("adapter_config.json", "adapter_model.safetensors", "training_state.json")
OPTIONAL_FILES = ("README.md", "chat_template.jinja", "tokenizer_config.json")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_state(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError(f"训练状态无效：{path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"训练状态必须是对象：{path}")
    return value


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="提升候选LoRA为正式适配器")
    parser.add_argument("source", type=Path)
    parser.add_argument("--target", type=Path, default=DEFAULT_ADAPTER_PATH)
    parser.add_argument("--backup-root", type=Path, default=Path("adapters/backups"))
    parser.add_argument("--allow-nonbest", action="store_true")
    args = parser.parse_args()

    for filename in REQUIRED_FILES:
        if not (args.source / filename).exists():
            raise FileNotFoundError(f"候选适配器缺少{filename}")
    source_state = read_state(args.source / "training_state.json")
    if (
        not args.allow_nonbest
        and source_state.get("selected_checkpoint") != "best_validation"
    ):
        raise ValueError("候选适配器不是按验证集选出的最佳检查点，拒绝提升")

    target_step = 0
    if (args.target / "training_state.json").exists():
        target_step = int(read_state(args.target / "training_state.json").get("step", 0) or 0)
    if args.target.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = args.backup_root / f"step-{target_step}-{stamp}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(args.target, backup)
        print(f"旧适配器已备份：{backup}")

    args.target.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for filename in REQUIRED_FILES + OPTIONAL_FILES:
        source_file = args.source / filename
        if not source_file.exists():
            continue
        temporary = args.target / f".{filename}.promoting"
        shutil.copy2(source_file, temporary)
        temporary.replace(args.target / filename)
        copied.append(filename)

    manifest = {
        "promoted_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(args.source),
        "target": str(args.target),
        "step": int(source_state.get("step", 0) or 0),
        "attempted_step": int(source_state.get("attempted_step", 0) or 0),
        "validation_loss": source_state.get("best_val_loss"),
        "initial_validation_loss": source_state.get("initial_val_loss"),
        "selected_checkpoint": source_state.get("selected_checkpoint"),
        "files": {
            filename: {
                "size_bytes": (args.target / filename).stat().st_size,
                "sha256": sha256(args.target / filename),
            }
            for filename in copied
        },
    }
    (args.target / "adapter_release.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
