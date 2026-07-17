"""下载升级版中文指令模型到项目本地目录。"""

from __future__ import annotations

import argparse
from pathlib import Path

from huggingface_hub import snapshot_download

from console_utils import configure_utf8_console


DEFAULT_MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
DEFAULT_LOCAL_DIR = Path("models/Qwen2.5-0.5B-Instruct")


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="下载本地中文指令模型")
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--local-dir", type=Path, default=DEFAULT_LOCAL_DIR)
    args = parser.parse_args()

    args.local_dir.mkdir(parents=True, exist_ok=True)
    print(f"开始下载：{args.model_id}")
    print(f"保存位置：{args.local_dir.resolve()}")
    snapshot_download(
        repo_id=args.model_id,
        local_dir=str(args.local_dir),
        ignore_patterns=["*.msgpack", "*.h5", "*.ot"],
    )
    print("模型下载完成。")


if __name__ == "__main__":
    main()
