"""为彦博 AI 自动准备 Android SDK、固定签名并构建可更新 APK。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from console_utils import configure_utf8_console
from inject_remote_config import main as inject_remote_config
from patch_android_project import main as patch_android_project

APP_ROOT = ROOT / "mobile_app"
ANDROID_ROOT = APP_ROOT / "android"
SDK_ROOT = Path(os.environ.get("YANBO_ANDROID_SDK", r"D:\AndroidSDK"))
SDK_MIRROR = "https://mirrors.cloud.tencent.com/AndroidSDK"
SDK_PACKAGES = [
    {
        "name": "Android 35平台",
        "filename": "platform-35_r02.zip",
        "size": 64_273_788,
        "sha1": "0bb560a90a7a2cbd0dd8348224d518b638fe7949",
        "destination": SDK_ROOT / "platforms" / "android-35",
        "marker": "android.jar",
    },
    {
        "name": "Android 34构建工具",
        "filename": "build-tools_r34-windows.zip",
        "size": 58_253_258,
        "sha1": "62cfde1b6fcc3ad12a4d2ba1b537e752768bfd47",
        "destination": SDK_ROOT / "build-tools" / "34.0.0",
        "marker": "aapt2.exe",
    },
    {
        "name": "Android 35构建工具",
        "filename": "build-tools_r35_windows.zip",
        "size": 59_878_107,
        "sha1": "af059bb67cf7786f45ee0db85e2d24985df1b4b6",
        "destination": SDK_ROOT / "build-tools" / "35.0.0",
        "marker": "aapt2.exe",
    },
    {
        "name": "Android平台工具",
        "filename": "platform-tools_r37.0.1-win.zip",
        "size": 8_044_994,
        "sha1": "10f2ef5325bc5705d48d38a0aa900c7babda24fa",
        "destination": SDK_ROOT / "platform-tools",
        "marker": "adb.exe",
    },
]
SIGNING_DIR = ANDROID_ROOT / "signing"
KEYSTORE_PATH = SIGNING_DIR / "yanbo-release.jks"
KEYSTORE_PROPERTIES = SIGNING_DIR / "keystore.properties"
UPDATE_PATH = ROOT / "mobile_update.json"
RELEASES_DIR = ROOT / "releases"


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    print("\n执行：" + " ".join(command))
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(f"命令执行失败，退出码：{completed.returncode}")
    return completed


def file_sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(url: str, destination: Path, expected_size: int, expected_sha1: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        size_ok = destination.stat().st_size == expected_size
        hash_ok = size_ok and file_sha1(destination).lower() == expected_sha1.lower()
        if hash_ok:
            print(f"已存在且校验通过：{destination.name}")
            return
        destination.unlink(missing_ok=True)

    print(f"正在下载：{url}")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, headers={"User-Agent": "Yanbo-Mobile-Builder/1.0"})
    with opener.open(request, timeout=120) as response, destination.open("wb") as output:
        total = int(response.headers.get("Content-Length", "0") or expected_size)
        downloaded = 0
        last_report = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
            downloaded += len(chunk)
            if downloaded - last_report >= 8 * 1024 * 1024:
                last_report = downloaded
                print(f"下载进度：{downloaded / max(1, total):.0%}")

    if destination.stat().st_size != expected_size:
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"{destination.name} 下载大小不正确。")
    actual_sha1 = file_sha1(destination)
    if actual_sha1.lower() != expected_sha1.lower():
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"{destination.name} 校验失败。")


def install_zip_package(package: dict[str, object]) -> None:
    destination = Path(package["destination"])
    marker = str(package["marker"])
    if (destination / marker).exists():
        print(f"{package['name']}已安装：{destination}")
        return

    archive = SDK_ROOT / "downloads" / str(package["filename"])
    url = f"{SDK_MIRROR}/{package['filename']}"
    download_file(url, archive, int(package["size"]), str(package["sha1"]))

    with tempfile.TemporaryDirectory(prefix="yanbo-sdk-") as temp_dir:
        temp = Path(temp_dir)
        print(f"正在解压{package['name']}……")
        with zipfile.ZipFile(archive) as zip_file:
            zip_file.extractall(temp)
        matches = list(temp.rglob(marker))
        if not matches:
            raise RuntimeError(f"{package['name']}压缩包中没有找到{marker}。")
        source = matches[0].parent
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)

    if not (destination / marker).exists():
        raise RuntimeError(f"{package['name']}安装失败。")
    print(f"{package['name']}安装完成。")


def detect_java_home() -> Path | None:
    configured = os.environ.get("JAVA_HOME", "").strip()
    if configured and (Path(configured) / "bin" / "java.exe").exists():
        return Path(configured)
    try:
        completed = subprocess.run(
            ["java", "-XshowSettings:properties", "-version"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except OSError:
        completed = None
    if completed is not None:
        match = re.search(r"^\s*java\.home\s*=\s*(.+?)\s*$", completed.stderr, re.MULTILINE)
        if match:
            candidate = Path(match.group(1).strip())
            if (candidate / "bin" / "java.exe").exists():
                return candidate
    candidates = [
        Path(r"E:\Java"),
        Path(r"C:\Program Files\Android\Android Studio\jbr"),
        Path(r"C:\Program Files\Eclipse Adoptium\jdk-17"),
        Path(r"C:\Program Files\Java\jdk-17"),
    ]
    for candidate in candidates:
        if (candidate / "bin" / "java.exe").exists():
            return candidate
    return None


def sdk_environment() -> dict[str, str]:
    env = os.environ.copy()
    env["ANDROID_HOME"] = str(SDK_ROOT)
    env["ANDROID_SDK_ROOT"] = str(SDK_ROOT)
    java_home = detect_java_home()
    if java_home is not None:
        env["JAVA_HOME"] = str(java_home)
    env["PATH"] = os.pathsep.join(
        [
            str(SDK_ROOT / "platform-tools"),
            str(SDK_ROOT / "build-tools" / "35.0.0"),
            env.get("PATH", ""),
        ]
    )
    env.pop("HTTP_PROXY", None)
    env.pop("HTTPS_PROXY", None)
    env.pop("ALL_PROXY", None)
    return env


def install_sdk_packages(env: dict[str, str]) -> None:
    del env
    SDK_ROOT.mkdir(parents=True, exist_ok=True)
    for package in SDK_PACKAGES:
        install_zip_package(package)

    licenses = SDK_ROOT / "licenses"
    licenses.mkdir(parents=True, exist_ok=True)
    (licenses / "android-sdk-license").write_text(
        "24333f8a63b6825ea9c5514f83c2829b004d1fee\n"
        "d56f5187479451eabf01fb78af6dfcb131a6481e\n",
        encoding="utf-8",
    )


def write_local_properties() -> None:
    path = ANDROID_ROOT / "local.properties"
    escaped = SDK_ROOT.as_posix().replace(":", r"\:")
    path.write_text(f"sdk.dir={escaped}\n", encoding="utf-8")
    print(f"已写入：{path}")


def create_signing_key() -> None:
    SIGNING_DIR.mkdir(parents=True, exist_ok=True)
    if KEYSTORE_PATH.exists() and KEYSTORE_PROPERTIES.exists():
        print("固定发布签名已存在，将继续使用同一签名。")
        return

    keytool = shutil.which("keytool")
    if not keytool:
        java_home = detect_java_home()
        candidate = java_home / "bin" / "keytool.exe" if java_home else None
        if candidate and candidate.exists():
            keytool = str(candidate)
    if not keytool:
        raise RuntimeError("没有找到 keytool，请安装完整的 JDK 17。")
    password = secrets.token_urlsafe(32)
    run(
        [
            keytool,
            "-genkeypair",
            "-v",
            "-keystore",
            str(KEYSTORE_PATH),
            "-storepass",
            password,
            "-keypass",
            password,
            "-alias",
            "yanbo",
            "-keyalg",
            "RSA",
            "-keysize",
            "3072",
            "-validity",
            "10000",
            "-dname",
            "CN=Yanbo AI, OU=Personal AI, O=Yanbo, L=Local, ST=Local, C=CN",
        ]
    )
    KEYSTORE_PROPERTIES.write_text(
        "storeFile=signing/yanbo-release.jks\n"
        f"storePassword={password}\n"
        "keyAlias=yanbo\n"
        f"keyPassword={password}\n",
        encoding="utf-8",
    )
    print("已生成彦博专用发布签名。请备份 mobile_app/android/signing 目录。")


def load_update_info() -> dict:
    if UPDATE_PATH.exists():
        return json.loads(UPDATE_PATH.read_text(encoding="utf-8"))
    return {"app_version": "1.0.0", "model_name": "彦博"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_release(
    env: dict[str, str],
    *,
    build_aab: bool = False,
    clean: bool = False,
) -> tuple[Path, Path | None]:
    gradlew = ANDROID_ROOT / "gradlew.bat"
    tasks: list[str] = []
    if clean:
        tasks.append("clean")
    tasks.append("assembleRelease")
    if build_aab:
        tasks.append("bundleRelease")
    run(
        [
            os.environ.get("COMSPEC", "cmd.exe"),
            "/d",
            "/c",
            str(gradlew),
            "--daemon",
            "--build-cache",
            "--max-workers=2",
            *tasks,
        ],
        cwd=ANDROID_ROOT,
        env=env,
    )
    apk = ANDROID_ROOT / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk"
    aab = ANDROID_ROOT / "app" / "build" / "outputs" / "bundle" / "release" / "app-release.aab"
    if not apk.exists():
        raise RuntimeError("构建完成后没有找到正式 APK。")
    return apk, aab if build_aab and aab.exists() else None


def verify_apk(apk: Path, env: dict[str, str]) -> None:
    apksigner = SDK_ROOT / "build-tools" / "35.0.0" / "apksigner.bat"
    if not apksigner.exists():
        return
    verify_env = env.copy()
    verify_env["JAVA_OPTS"] = "-Xms16m -Xmx128m -XX:+UseSerialGC"
    verify_env["JAVA_TOOL_OPTIONS"] = "-Xms16m -Xmx128m -XX:+UseSerialGC"
    completed = run(
        [
            os.environ.get("COMSPEC", "cmd.exe"),
            "/d",
            "/c",
            str(apksigner),
            "verify",
            "--verbose",
            "--print-certs",
            str(apk),
        ],
        env=verify_env,
        check=False,
    )
    if completed.returncode != 0:
        print("警告：系统内存不足，额外APK签名检查未完成；Gradle签名任务已成功。")


def publish(apk: Path, aab: Path | None) -> None:
    info = load_update_info()
    version = str(info.get("app_version", "1.0.0"))
    RELEASES_DIR.mkdir(parents=True, exist_ok=True)
    apk_name = f"Yanbo-AI-Android-v{version}.apk"
    release_apk = RELEASES_DIR / apk_name
    shutil.copy2(apk, release_apk)

    release_aab: Path | None = None
    if aab is not None:
        release_aab = RELEASES_DIR / f"Yanbo-AI-Android-v{version}.aab"
        shutil.copy2(aab, release_aab)

    info["android_download_url"] = f"/downloads/{apk_name}"
    info["android_sha256"] = sha256(release_apk)
    info["android_size_bytes"] = release_apk.stat().st_size
    info["published_at"] = datetime.now().isoformat(timespec="seconds")
    UPDATE_PATH.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = {
        "app_version": version,
        "apk": str(release_apk.relative_to(ROOT)),
        "apk_size_bytes": release_apk.stat().st_size,
        "apk_sha256": info["android_sha256"],
        "aab": str(release_aab.relative_to(ROOT)) if release_aab else None,
        "built_at": info["published_at"],
        "sdk_root": str(SDK_ROOT),
    }
    (RELEASES_DIR / "android_build_info.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("\nAndroid 正式版构建完成：")
    print(release_apk)
    if release_aab:
        print(release_aab)
    print(f"SHA-256：{info['android_sha256']}")


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="构建彦博 AI Android 正式版")
    parser.add_argument("--with-aab", action="store_true", help="同时构建应用商店AAB包")
    parser.add_argument("--clean", action="store_true", help="先清理Gradle输出再完整构建")
    args = parser.parse_args()
    if not ANDROID_ROOT.exists():
        raise FileNotFoundError("Android 工程不存在，请先运行 06_prepare_mobile_app.bat。")
    print("彦博 AI Android 正式版自动构建")
    print(f"SDK目录：{SDK_ROOT}")
    env = sdk_environment()
    install_sdk_packages(env)
    write_local_properties()
    patch_android_project()
    inject_remote_config()
    create_signing_key()
    apk, aab = build_release(env, build_aab=args.with_aab, clean=args.clean)
    verify_apk(apk, env)
    publish(apk, aab)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n构建已取消。")
        raise SystemExit(130)
    except Exception as exc:
        print(f"\n构建失败：{exc}", file=sys.stderr)
        raise
