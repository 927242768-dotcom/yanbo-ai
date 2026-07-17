"""彦博公网服务后台守护程序：登录后自动启动，并在异常退出后自动恢复。"""

from __future__ import annotations

import json
import msvcrt
import os
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from remote_access_config import load_remote_access_config
from secure_mobile_access import ensure_public_service, local_server_ready


ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / ".runtime"
LOCK_PATH = RUNTIME_DIR / "remote_service.lock"
LOG_PATH = RUNTIME_DIR / "remote_service.log"


def log(message: str) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if LOG_PATH.exists() and LOG_PATH.stat().st_size > 1024 * 1024:
        LOG_PATH.replace(LOG_PATH.with_suffix(".log.old"))
    with LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")


def public_service_ready() -> bool:
    """直接检查公网 HTTPS，不再周期性启动 Tailscale 命令行进程。"""
    try:
        public_url = str(load_remote_access_config().get("public_url", "")).rstrip("/")
        if not public_url:
            return False
        request = urllib.request.Request(
            public_url + "/api/status",
            headers={"User-Agent": "Yanbo-Service-Watch/1.0"},
        )
        with urllib.request.urlopen(request, timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return response.status == 200 and bool(payload.get("ok"))
    except Exception:
        return False


def acquire_single_instance():
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    lock_file = LOCK_PATH.open("a+b")
    if LOCK_PATH.stat().st_size == 0:
        lock_file.write(b"0")
        lock_file.flush()
    lock_file.seek(0)
    try:
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock_file.close()
        return None
    return lock_file


def main() -> None:
    lock_file = acquire_single_instance()
    if lock_file is None:
        return
    log(f"后台守护程序启动，PID={os.getpid()}")
    last_public_check = 0.0
    last_healthy_log = 0.0
    public_failures = 0
    while True:
        try:
            now = time.monotonic()
            server_ready = local_server_ready(require_token=True)
            if not server_ready:
                time.sleep(1)
                if not local_server_ready(require_token=True):
                    url = ensure_public_service(background=True)
                    last_public_check = time.monotonic()
                    last_healthy_log = last_public_check
                    public_failures = 0
                    log(f"本地服务已快速恢复，公网地址：{url}")
            elif now - last_public_check >= 15:
                last_public_check = now
                if public_service_ready():
                    public_failures = 0
                    if now - last_healthy_log >= 600:
                        log("本地服务与公网 HTTPS 均正常")
                        last_healthy_log = now
                else:
                    public_failures += 1
                    if public_failures >= 2:
                        url = ensure_public_service(background=True)
                        log(f"公网隧道连续检查失败后已恢复：{url}")
                        public_failures = 0
                        last_healthy_log = time.monotonic()
        except Exception as exc:
            log(f"启动或检查失败：{exc}")
        time.sleep(5)


if __name__ == "__main__":
    main()
