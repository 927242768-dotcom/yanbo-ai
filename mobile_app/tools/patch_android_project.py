"""修正 Capacitor Android 工程的镜像、Java 17和局域网连接配置。"""

from __future__ import annotations

import sys
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
ROOT = APP_ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from console_utils import configure_utf8_console

ANDROID = APP_ROOT / "android"

MIRROR_BUILDSCRIPT = """repositories {
        maven { url 'https://maven.aliyun.com/repository/google' }
        maven { url 'https://maven.aliyun.com/repository/central' }
        maven { url 'https://maven.aliyun.com/repository/gradle-plugin' }
        google()
        mavenCentral()"""

MIRROR_PROJECT = """repositories {
    maven { url 'https://maven.aliyun.com/repository/google' }
    maven { url 'https://maven.aliyun.com/repository/central' }
    maven { url 'https://maven.aliyun.com/repository/public' }
    google()
    mavenCentral()"""


def replace_once(path: Path, old: str, new: str) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    if new in text:
        return False
    if old not in text:
        return False
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True


def patch_java(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    patched = text.replace("JavaVersion.VERSION_21", "JavaVersion.VERSION_17")
    if patched == text:
        return False
    path.write_text(patched, encoding="utf-8")
    return True


def patch_repositories(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    original = text
    text = text.replace(
        "repositories {\n        google()\n        mavenCentral()",
        MIRROR_BUILDSCRIPT,
    )
    text = text.replace(
        "repositories {\n    google()\n    mavenCentral()",
        MIRROR_PROJECT,
    )
    if text == original:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def patch_root_build() -> bool:
    path = ANDROID / "build.gradle"
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    original = text
    text = text.replace(
        "buildscript {\n    \n    repositories {\n        google()\n        mavenCentral()",
        "buildscript {\n    \n    " + MIRROR_BUILDSCRIPT,
    )
    text = text.replace(
        "allprojects {\n    repositories {\n        google()\n        mavenCentral()",
        "allprojects {\n    " + MIRROR_PROJECT,
    )
    if text == original:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def patch_wrapper() -> bool:
    path = ANDROID / "gradle" / "wrapper" / "gradle-wrapper.properties"
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    original = text
    for suffix in ("-all.zip", "-bin.zip"):
        text = text.replace(
            f"https\\://services.gradle.org/distributions/gradle-8.11.1{suffix}",
            "https\\://mirrors.cloud.tencent.com/gradle/gradle-8.11.1-bin.zip",
        )
    text = text.replace("networkTimeout=10000", "networkTimeout=60000")
    if text == original:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def patch_manifest() -> bool:
    path = ANDROID / "app" / "src" / "main" / "AndroidManifest.xml"
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    original = text
    if "android:usesCleartextTraffic" not in text:
        old = '<application\n        android:allowBackup="true"'
        new = '<application\n        android:allowBackup="true"\n        android:usesCleartextTraffic="true"'
        text = text.replace(old, new, 1)
    if "android.permission.ACCESS_NETWORK_STATE" not in text:
        marker = '    <uses-permission android:name="android.permission.INTERNET" />'
        replacement = marker + '\n    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />'
        text = text.replace(marker, replacement, 1)
    if text == original:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def main() -> None:
    configure_utf8_console()
    changed: list[str] = []
    files = [
        APP_ROOT / "node_modules" / "@capacitor" / "android" / "capacitor" / "build.gradle",
        ANDROID / "capacitor-cordova-android-plugins" / "build.gradle",
    ]
    for path in files:
        if patch_repositories(path):
            changed.append(str(path.relative_to(ROOT)))
        if patch_java(path):
            changed.append(str(path.relative_to(ROOT)) + " [Java17]")

    generated = ANDROID / "app" / "capacitor.build.gradle"
    if patch_java(generated):
        changed.append(str(generated.relative_to(ROOT)) + " [Java17]")
    if patch_root_build():
        changed.append("mobile_app/android/build.gradle")
    if patch_wrapper():
        changed.append("mobile_app/android/gradle/wrapper/gradle-wrapper.properties")
    if patch_manifest():
        changed.append("mobile_app/android/app/src/main/AndroidManifest.xml")

    if changed:
        print("Android工程补丁已应用：")
        for item in changed:
            print("- " + item)
    else:
        print("Android工程配置已经是最新状态。")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"补丁失败：{exc}", file=sys.stderr)
        raise
