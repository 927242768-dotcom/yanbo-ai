"""通过 Tailscale Funnel 为彦博手机端提供跨网络 HTTPS 访问。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from console_utils import configure_utf8_console
from remote_access_config import ensure_remote_access_config
from web_chat import stop_stale_web_servers


ROOT = Path(__file__).resolve().parent
TAILSCALE = Path(r"C:\Program Files\Tailscale\tailscale.exe")
LOCAL_PORT = 7860
HTTPS_PORT = 443
PUBLIC_PATH = "/yanbo"
LEGACY_HTTPS_PORT = 8443


def run(command: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(detail or f"命令执行失败：{completed.returncode}")
    return completed


def local_server_ready(require_token: bool = True) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{LOCAL_PORT}/api/status", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return response.status == 200 and (not require_token or bool(payload.get("auth_required")))
    except Exception:
        return False


def start_local_server(background: bool = False) -> None:
    if local_server_ready(require_token=True):
        return
    stop_stale_web_servers("127.0.0.1", LOCAL_PORT)
    creationflags = 0
    stdout = None
    stderr = None
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW if background else subprocess.CREATE_NEW_CONSOLE
    if background:
        stdout = subprocess.DEVNULL
        stderr = subprocess.DEVNULL
    subprocess.Popen(
        [
            sys.executable,
            "web_chat.py",
            "--host",
            "127.0.0.1",
            "--port",
            str(LOCAL_PORT),
            "--no-browser",
            "--require-remote-token",
        ],
        cwd=ROOT,
        creationflags=creationflags,
        stdout=stdout,
        stderr=stderr,
    )
    for _ in range(60):
        time.sleep(0.5)
        if local_server_ready(require_token=True):
            return
    raise RuntimeError("彦博安全远程服务启动超时。")


def ensure_public_service(background: bool = False) -> str:
    if not TAILSCALE.exists():
        raise FileNotFoundError("没有找到Tailscale，请先安装并在电脑端登录。")

    status = json.loads(run([str(TAILSCALE), "status", "--json"]).stdout)
    if status.get("BackendState") != "Running":
        raise RuntimeError("Tailscale尚未运行。")
    dns_name = str(status.get("Self", {}).get("DNSName", "")).rstrip(".")
    if not dns_name:
        raise RuntimeError("没有取得本机Tailscale域名。")

    public_url = f"https://{dns_name}{PUBLIC_PATH}"
    ensure_remote_access_config(public_url)
    start_local_server(background=background)

    standard_result = run(
        [
            str(TAILSCALE),
            "funnel",
            "--bg",
            "--yes",
            f"--https={HTTPS_PORT}",
            f"--set-path={PUBLIC_PATH}",
            f"http://127.0.0.1:{LOCAL_PORT}",
        ],
        check=False,
    )
    if standard_result.returncode != 0:
        detail = (standard_result.stderr or standard_result.stdout).strip()
        raise RuntimeError("标准443公网HTTPS隧道启动失败：" + detail)

    legacy_result = run(
        [
            str(TAILSCALE),
            "funnel",
            "--bg",
            "--yes",
            f"--https={LEGACY_HTTPS_PORT}",
            f"http://127.0.0.1:{LOCAL_PORT}",
        ],
        check=False,
    )
    if legacy_result.returncode != 0:
        detail = (legacy_result.stderr or legacy_result.stdout).strip()
        raise RuntimeError("备用8443公网HTTPS隧道启动失败：" + detail)
    return public_url


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="启动彦博公网手机服务")
    parser.add_argument("--background", action="store_true", help="无窗口后台运行")
    args = parser.parse_args()
    public_url = ensure_public_service(background=args.background)
    if not args.background:
        print("\n彦博公网手机服务已启动：")
        print(public_url)
        print("手机可直接使用移动数据、其他Wi-Fi或异地网络连接。")


if __name__ == "__main__":
    main()
