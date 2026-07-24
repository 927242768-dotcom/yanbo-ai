"""准备彦博-v3兼容训练模型到项目本地目录。"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from huggingface_hub import snapshot_download

from console_utils import configure_utf8_console


DEFAULT_LOCAL_DIR = Path("models/yanbo-v3-compat")


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="准备彦博-v3兼容训练模型")
    parser.add_argument(
        "--model-id",
        default=os.environ.get("YANBO_COMPAT_MODEL_ID", "").strip(),
        help="兼容训练模型来源；也可通过YANBO_COMPAT_MODEL_ID设置",
    )
    parser.add_argument("--local-dir", type=Path, default=DEFAULT_LOCAL_DIR)
    args = parser.parse_args()

    if (args.local_dir / "config.json").exists():
        print(f"彦博-v3兼容训练模型已存在：{args.local_dir.resolve()}")
        return
    if not args.model_id:
        raise RuntimeError(
            "未找到彦博-v3兼容训练模型。请先恢复models/yanbo-v3-compat，"
            "或通过YANBO_COMPAT_MODEL_ID指定下载来源。"
        )

    args.local_dir.mkdir(parents=True, exist_ok=True)
    print("开始准备彦博-v3兼容训练模型……")
    print(f"保存位置：{args.local_dir.resolve()}")
    snapshot_download(
        repo_id=args.model_id,
        local_dir=str(args.local_dir),
        ignore_patterns=["*.msgpack", "*.h5", "*.ot"],
    )
    print("彦博-v3兼容训练模型准备完成。")


if __name__ == "__main__":
    main()
