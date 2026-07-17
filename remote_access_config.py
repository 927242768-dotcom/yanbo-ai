"""彦博远程访问配置：生成并读取公网地址与访问令牌。"""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "remote_access.json"
DEFAULT_PUBLIC_URL = "https://laptop-m4o3b2hb.tail692923.ts.net/yanbo"
DEFAULT_LEGACY_PUBLIC_URL = "https://laptop-m4o3b2hb.tail692923.ts.net:8443"


def _normalize_url(value: str) -> str:
    url = value.strip().rstrip("/")
    if not url.startswith("https://"):
        raise ValueError("远程访问地址必须使用HTTPS。")
    return url


def ensure_remote_access_config(public_url: str | None = None) -> dict[str, str]:
    """确保远程配置存在；首次运行时生成高强度随机访问令牌。"""
    existing: dict[str, Any] = {}
    if CONFIG_PATH.exists():
        try:
            loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, ValueError, TypeError):
            existing = {}

    token = str(existing.get("access_token", "")).strip()
    if len(token) < 32:
        token = secrets.token_urlsafe(32)

    selected_public_url = public_url or str(existing.get("public_url") or DEFAULT_PUBLIC_URL)
    legacy_public_url = str(existing.get("legacy_public_url") or DEFAULT_LEGACY_PUBLIC_URL)
    payload = {
        "public_url": _normalize_url(selected_public_url),
        "legacy_public_url": _normalize_url(legacy_public_url),
        "access_token": token,
    }
    CONFIG_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def load_remote_access_config() -> dict[str, str]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError("远程访问配置不存在，请先运行07_secure_mobile_access.bat。")
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("远程访问配置格式错误。")
    public_url = _normalize_url(str(payload.get("public_url", "")))
    token = str(payload.get("access_token", "")).strip()
    if len(token) < 32:
        raise ValueError("远程访问令牌无效，请重新运行07_secure_mobile_access.bat。")
    legacy_public_url = _normalize_url(
        str(payload.get("legacy_public_url") or DEFAULT_LEGACY_PUBLIC_URL)
    )
    return {
        "public_url": public_url,
        "legacy_public_url": legacy_public_url,
        "access_token": token,
    }
