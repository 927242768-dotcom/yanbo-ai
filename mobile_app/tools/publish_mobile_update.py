"""发布彦博 AI 手机应用新版本并生成可覆盖安装的 Android APK。"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from console_utils import configure_utf8_console

APP_ROOT = ROOT / "mobile_app"
UPDATE_PATH = ROOT / "mobile_update.json"
WEB_INDEX = APP_ROOT / "www" / "index.html"
ANDROID_BUILD = APP_ROOT / "android" / "app" / "build.gradle"
IOS_PROJECT = APP_ROOT / "ios" / "App" / "App.xcodeproj" / "project.pbxproj"
SERVICE_WORKER = ROOT / "mobile" / "service-worker.js"
PACKAGE_JSON = APP_ROOT / "package.json"
PACKAGE_LOCK = APP_ROOT / "package-lock.json"


def parse_version(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value.strip())
    if not match:
        raise ValueError("版本号必须使用 major.minor.patch，例如 1.0.1。")
    return tuple(map(int, match.groups()))


def bump_patch(value: str) -> str:
    major, minor, patch = parse_version(value)
    return f"{major}.{minor}.{patch + 1}"


def version_code(value: str) -> int:
    major, minor, patch = parse_version(value)
    if minor > 99 or patch > 99:
        raise ValueError("minor和patch不能超过99。")
    return major * 10000 + minor * 100 + patch


def replace_regex(path: Path, pattern: str, replacement: str, count: int = 0) -> None:
    text = path.read_text(encoding="utf-8")
    updated, changed = re.subn(pattern, replacement, text, count=count, flags=re.MULTILINE)
    if changed == 0:
        raise RuntimeError(f"无法在{path}中更新版本信息。")
    path.write_text(updated, encoding="utf-8")


def update_json_version(path: Path, version: str) -> None:
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["version"] = version
    if path == PACKAGE_LOCK and isinstance(payload.get("packages"), dict):
        root_package = payload["packages"].get("")
        if isinstance(root_package, dict):
            root_package["version"] = version
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(command: list[str], cwd: Path) -> None:
    print("\n执行：" + " ".join(command))
    completed = subprocess.run(command, cwd=cwd, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"步骤执行失败，退出码：{completed.returncode}")


def sync_native_projects(full: bool = False) -> None:
    cap = APP_ROOT / "node_modules" / ".bin" / "cap.cmd"
    if not cap.exists():
        raise FileNotFoundError("手机依赖未安装，请先运行06_prepare_mobile_app.bat。")
    command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(cap)]
    if full:
        run([*command, "sync"], APP_ROOT)
    else:
        run([*command, "copy", "android"], APP_ROOT)
    run([sys.executable, str(APP_ROOT / "tools" / "patch_android_project.py")], APP_ROOT)


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="发布彦博 AI 手机应用更新")
    parser.add_argument("--version", help="指定新版本，例如1.0.1；不填则自动增加patch版本")
    parser.add_argument("--note", action="append", default=[], help="更新说明，可重复填写")
    parser.add_argument("--force", action="store_true", help="要求旧版本强制更新")
    parser.add_argument("--no-build", action="store_true", help="只更新版本文件，不构建APK")
    parser.add_argument("--full", action="store_true", help="执行完整发布：构建AAB、iOS工程和完整发布包")
    parser.add_argument("--clean", action="store_true", help="清理Gradle输出后重新构建")
    args = parser.parse_args()

    info = json.loads(UPDATE_PATH.read_text(encoding="utf-8"))
    current = str(info.get("app_version", "1.0.0"))
    new_version = args.version or bump_patch(current)
    parse_version(new_version)
    if parse_version(new_version) <= parse_version(current):
        raise ValueError(f"新版本{new_version}必须高于当前版本{current}。")

    notes = args.note or [
        "优化手机端稳定性与使用体验",
        "同步最新彦博模型能力",
    ]
    info["app_version"] = new_version
    info["minimum_app_version"] = new_version if args.force else str(info.get("minimum_app_version", "1.0.0"))
    info["force_update"] = bool(args.force)
    info["release_notes"] = notes
    info["android_download_url"] = ""
    info.pop("android_sha256", None)
    info.pop("android_size_bytes", None)
    UPDATE_PATH.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    replace_regex(WEB_INDEX, r"const APP_VERSION='[^']+';", f"const APP_VERSION='{new_version}';", count=1)
    replace_regex(ANDROID_BUILD, r"versionCode\s+\d+", f"versionCode {version_code(new_version)}", count=1)
    replace_regex(ANDROID_BUILD, r'versionName\s+"[^"]+"', f'versionName "{new_version}"', count=1)
    replace_regex(
        SERVICE_WORKER,
        r"const CACHE_NAME = 'yanbo-mobile-v3-app-[^']+';",
        f"const CACHE_NAME = 'yanbo-mobile-v3-app-{new_version}';",
        count=1,
    )
    update_json_version(PACKAGE_JSON, new_version)
    update_json_version(PACKAGE_LOCK, new_version)

    if IOS_PROJECT.exists():
        replace_regex(IOS_PROJECT, r"MARKETING_VERSION = [^;]+;", f"MARKETING_VERSION = {new_version};")
        replace_regex(IOS_PROJECT, r"CURRENT_PROJECT_VERSION = \d+;", f"CURRENT_PROJECT_VERSION = {version_code(new_version)};")

    sync_native_projects(full=args.full)
    print(f"应用版本已从{current}更新为{new_version}。")

    if not args.no_build:
        build_command = [sys.executable, str(APP_ROOT / "tools" / "build_android_release.py")]
        if args.full:
            run([sys.executable, str(APP_ROOT / "tools" / "generate_app_assets.py")], ROOT)
            build_command.append("--with-aab")
        if args.clean:
            build_command.append("--clean")
        run(build_command, ROOT)
        if args.full:
            run([sys.executable, str(APP_ROOT / "tools" / "package_ios_project.py")], ROOT)
            run([sys.executable, str(APP_ROOT / "tools" / "package_mobile_release.py")], ROOT)
            print("\n手机应用完整版本发布完成。")
        else:
            print("\nAndroid快速更新发布完成；已跳过AAB、iOS工程和完整发布包。")
        print(f"Android APK：releases/Yanbo-AI-Android-v{new_version}.apk")
    else:
        print("已跳过APK构建。")


if __name__ == "__main__":
    main()
