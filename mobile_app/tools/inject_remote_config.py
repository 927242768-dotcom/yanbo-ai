"""把远程服务器地址与访问令牌注入 Android/iOS 原生应用资源。"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from console_utils import configure_utf8_console
from remote_access_config import ensure_remote_access_config


SOURCE_INDEX = ROOT / "mobile_app" / "www" / "index.html"

TARGETS = [
    ROOT / "mobile_app" / "android" / "app" / "src" / "main" / "assets" / "public" / "index.html",
    ROOT / "mobile_app" / "ios" / "App" / "App" / "public" / "index.html",
]


def inject_file(
    path: Path,
    public_url: str,
    legacy_public_url: str,
    access_token: str,
) -> bool:
    if not path.exists():
        return False
    if not SOURCE_INDEX.exists():
        raise FileNotFoundError("手机端最新页面不存在。")
    text = SOURCE_INDEX.read_text(encoding="utf-8")
    text, server_changes = re.subn(
        r"const DEFAULT_SERVER='[^']*';",
        f"const DEFAULT_SERVER='{public_url}';",
        text,
        count=1,
    )
    text, legacy_changes = re.subn(
        r"const LEGACY_SERVER='[^']*';",
        f"const LEGACY_SERVER='{legacy_public_url}';",
        text,
        count=1,
    )
    text, token_changes = re.subn(
        r"const DEFAULT_ACCESS_TOKEN='[^']*';",
        f"const DEFAULT_ACCESS_TOKEN='{access_token}';",
        text,
        count=1,
    )
    if server_changes != 1 or legacy_changes != 1 or token_changes != 1:
        raise RuntimeError(f"无法向{path}注入远程访问配置。")
    path.write_text(text, encoding="utf-8")
    return True


def main() -> None:
    configure_utf8_console()
    config = ensure_remote_access_config()
    injected = []
    for target in TARGETS:
        if inject_file(
            target,
            config["public_url"],
            config["legacy_public_url"],
            config["access_token"],
        ):
            injected.append(str(target.relative_to(ROOT)))
    if not injected:
        raise FileNotFoundError("没有找到已同步的Android或iOS应用资源，请先运行Capacitor同步。")
    print("已向原生应用注入安全远程访问配置：")
    for path in injected:
        print(path)


if __name__ == "__main__":
    main()
