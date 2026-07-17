"""验证彦博公网地址、令牌校验和Funnel状态。"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from console_utils import configure_utf8_console
from remote_access_config import load_remote_access_config


def main() -> None:
    configure_utf8_console()
    config = load_remote_access_config()
    base = config["public_url"]

    with urllib.request.urlopen(base + "/api/status", timeout=20) as response:
        status = json.loads(response.read().decode("utf-8"))
    if not status.get("ok") or not status.get("auth_required"):
        raise RuntimeError("公网服务未启用令牌保护。")

    denied = False
    try:
        urllib.request.urlopen(base + "/api/auth-check", timeout=20)
    except urllib.error.HTTPError as exc:
        denied = exc.code == 401
    if not denied:
        raise RuntimeError("无令牌请求没有被正确拒绝。")

    request = urllib.request.Request(
        base + "/api/auth-check",
        headers={"X-Yanbo-Token": config["access_token"]},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        authenticated = json.loads(response.read().decode("utf-8"))
    if not authenticated.get("ok"):
        raise RuntimeError("携带正确令牌后仍无法访问。")

    def verify_chat_mode(mode: str, request_id: str) -> None:
        payload = json.dumps(
            {
                "request_id": request_id,
                "mode": mode,
                "message": "6+7等于多少？",
                "history": [],
            },
            ensure_ascii=False,
        ).encode("utf-8")
        chat_request = urllib.request.Request(
            base + "/chat-stream",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Yanbo-Token": config["access_token"],
                "X-Yanbo-Session": "remote-mode-verification",
            },
            method="POST",
        )
        with urllib.request.urlopen(chat_request, timeout=90) as response:
            events = [
                json.loads(line.decode("utf-8"))
                for line in response
                if line.strip()
            ]
        text = "".join(
            str(event.get("text", ""))
            for event in events
            if event.get("type") == "delta"
        )
        completed = any(
            event.get("type") == "done" and event.get("mode") == mode
            for event in events
        )
        if "13" not in text or not completed:
            raise RuntimeError(f"公网{mode}模式流式聊天验证失败。")

    verify_chat_mode("thinking", "remote-thinking-verification")
    verify_chat_mode("fast", "remote-fast-verification")

    update = json.loads(Path("mobile_update.json").read_text(encoding="utf-8"))
    download_path = str(update.get("android_download_url", ""))
    if not download_path:
        raise RuntimeError("没有找到Android下载地址。")
    denied_download = False
    try:
        urllib.request.urlopen(base + download_path, timeout=20)
    except urllib.error.HTTPError as exc:
        denied_download = exc.code == 401
    if not denied_download:
        raise RuntimeError("未授权用户仍可下载Android安装包。")

    query = urllib.parse.urlencode({"token": config["access_token"]})
    with urllib.request.urlopen(base + download_path + "?" + query, timeout=20) as response:
        signature = response.read(4)
    if not signature.startswith(b"PK"):
        raise RuntimeError("授权下载返回的文件不是有效APK。")

    print("公网远程访问验证通过：")
    print(base)
    print(f"模型：{status.get('model', '未知')}")
    print("聊天令牌保护：正常")
    print("彦博-思考公网流式聊天：正常")
    print("彦博-快速公网流式聊天：正常")
    print("安装包下载保护：正常")


if __name__ == "__main__":
    main()
