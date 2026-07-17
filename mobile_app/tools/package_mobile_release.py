"""生成彦博手机访问二维码和完整手机发布包。"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import cv2


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from console_utils import configure_utf8_console
from remote_access_config import load_remote_access_config

RELEASES = ROOT / "releases"
UPDATE_PATH = ROOT / "mobile_update.json"
MANUAL = ROOT / "手机应用安装与更新说明.md"


def generate_qr(path: Path, public_url: str) -> None:
    encoder = cv2.QRCodeEncoder_create()
    image = encoder.encode(public_url)
    image = cv2.resize(image, (900, 900), interpolation=cv2.INTER_NEAREST)
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("二维码编码失败。")
    path.write_bytes(encoded.tobytes())


def main() -> None:
    configure_utf8_console()
    info = json.loads(UPDATE_PATH.read_text(encoding="utf-8"))
    remote = load_remote_access_config()
    public_url = remote["public_url"].rstrip("/") + "/"
    version = str(info.get("app_version", "1.0.0"))
    RELEASES.mkdir(parents=True, exist_ok=True)

    qr_path = RELEASES / "彦博手机访问二维码.png"
    generate_qr(qr_path, public_url)

    apk = RELEASES / f"Yanbo-AI-Android-v{version}.apk"
    ios = RELEASES / f"Yanbo-AI-iOS-Project-v{version}.zip"
    if not apk.exists():
        raise FileNotFoundError(f"没有找到Android安装包：{apk}")
    if not ios.exists():
        raise FileNotFoundError(f"没有找到iOS工程包：{ios}")

    package_path = RELEASES / f"Yanbo-Mobile-Release-v{version}.zip"
    package_path.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="yanbo-mobile-release-") as temp_dir:
        temp = Path(temp_dir)
        shutil.copy2(apk, temp / apk.name)
        shutil.copy2(ios, temp / ios.name)
        shutil.copy2(qr_path, temp / qr_path.name)
        shutil.copy2(MANUAL, temp / MANUAL.name)
        (temp / "手机访问地址.txt").write_text(
            "彦博 AI 公网手机地址：\n"
            f"{public_url}\n\n"
            "使用前请在电脑运行 07_secure_mobile_access.bat。\n"
            "Android正式安装包已内置访问令牌，无需手机安装Tailscale。\n",
            encoding="utf-8",
        )
        with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for file in sorted(temp.iterdir()):
                archive.write(file, arcname=file.name)

    info["mobile_release_download_url"] = f"/downloads/{package_path.name}"
    info["mobile_release_size_bytes"] = package_path.stat().st_size
    UPDATE_PATH.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("手机发布包已生成：")
    print(package_path)
    print("公网访问二维码：")
    print(qr_path)


if __name__ == "__main__":
    main()
