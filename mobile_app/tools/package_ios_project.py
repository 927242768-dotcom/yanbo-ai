"""打包彦博 AI iOS 原生工程，供在 macOS/Xcode 中签名构建。"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from console_utils import configure_utf8_console
from inject_remote_config import main as inject_remote_config

IOS_ROOT = ROOT / "mobile_app" / "ios"
RELEASES = ROOT / "releases"
UPDATE_PATH = ROOT / "mobile_update.json"


def ignore(directory: str, names: list[str]) -> set[str]:
    ignored = {
        ".DS_Store",
        "Pods",
        "build",
        "DerivedData",
        "xcuserdata",
        ".gradle",
    }
    return {name for name in names if name in ignored or name.endswith(".xcuserstate")}


def main() -> None:
    configure_utf8_console()
    if not IOS_ROOT.exists():
        raise FileNotFoundError("iOS工程不存在，请先运行06_prepare_mobile_app.bat。")

    inject_remote_config()
    info = json.loads(UPDATE_PATH.read_text(encoding="utf-8"))
    version = str(info.get("app_version", "1.0.0"))
    RELEASES.mkdir(parents=True, exist_ok=True)
    base_name = RELEASES / f"Yanbo-AI-iOS-Project-v{version}"
    archive = Path(str(base_name) + ".zip")
    archive.unlink(missing_ok=True)

    temp_copy = RELEASES / f".ios-package-{version}"
    if temp_copy.exists():
        shutil.rmtree(temp_copy)
    shutil.copytree(IOS_ROOT, temp_copy, ignore=ignore)

    readme = temp_copy / "BUILD_ON_MAC.md"
    readme.write_text(
        "# 彦博 AI iOS 构建说明\n\n"
        "1. 在macOS安装Xcode。\n"
        "2. 打开 `App/App.xcworkspace`；若不存在，则先在 `App` 目录执行 `pod install`。\n"
        "3. 在Signing & Capabilities中选择自己的Apple开发团队。\n"
        "4. 连接iPhone后直接运行，或使用Archive生成发布包。\n\n"
        "模型继续运行在彦博服务器端，iPhone应用负责聊天、拍照和图片上传。\n",
        encoding="utf-8",
    )

    shutil.make_archive(str(base_name), "zip", root_dir=temp_copy)
    shutil.rmtree(temp_copy)

    info["ios_project_download_url"] = f"/downloads/{archive.name}"
    info["ios_project_size_bytes"] = archive.stat().st_size
    info["ios_project_published_at"] = datetime.now().isoformat(timespec="seconds")
    UPDATE_PATH.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("iOS原生工程包已生成：")
    print(archive)
    print(f"大小：{archive.stat().st_size} 字节")


if __name__ == "__main__":
    main()
