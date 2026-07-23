"""彦博能力分层配置：快速、思考与专家模式的模型和生成参数。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "capability_config.json"
VALID_BACKENDS = {"auto", "native", "fallback", "remote"}


@dataclass(frozen=True)
class ModeProfile:
    mode: str
    display_name: str
    backend: str
    model: str
    num_ctx: int
    text_max_tokens: int
    image_max_tokens: int
    text_temperature: float
    image_temperature: float
    direct_vision: bool = True
    knowledge_base: bool = True
    remote_api_url: str = ""
    remote_model: str = ""
    remote_api_key_env: str = "YANBO_EXPERT_API_KEY"

    @property
    def remote_api_key(self) -> str:
        return os.environ.get(self.remote_api_key_env, "").strip()

    @property
    def effective_backend(self) -> str:
        if self.backend != "auto":
            return self.backend
        if self.remote_api_url and self.remote_model:
            return "remote"
        return "native"


DEFAULTS: dict[str, ModeProfile] = {
    "fast": ModeProfile(
        mode="fast",
        display_name="彦博-快速",
        backend="native",
        model="yanbo-v3:latest",
        num_ctx=8192,
        text_max_tokens=4096,
        image_max_tokens=4096,
        text_temperature=0.25,
        image_temperature=0.22,
        direct_vision=False,
    ),
    "thinking": ModeProfile(
        mode="thinking",
        display_name="彦博-思考",
        backend="native",
        model="yanbo-v3:latest",
        num_ctx=12288,
        text_max_tokens=8192,
        image_max_tokens=8192,
        text_temperature=0.34,
        image_temperature=0.26,
        direct_vision=False,
    ),
    "expert": ModeProfile(
        mode="expert",
        display_name="彦博-专家",
        backend="auto",
        model="yanbo-v3:latest",
        num_ctx=16384,
        text_max_tokens=12288,
        image_max_tokens=12288,
        text_temperature=0.20,
        image_temperature=0.18,
        direct_vision=False,
    ),
}


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


def _merge_profile(default: ModeProfile, raw: Any) -> ModeProfile:
    if not isinstance(raw, dict):
        return default
    backend = str(raw.get("backend", default.backend)).strip().lower()
    if backend not in VALID_BACKENDS:
        backend = default.backend
    return replace(
        default,
        display_name=str(raw.get("display_name", default.display_name)).strip() or default.display_name,
        backend=backend,
        model=str(raw.get("model", default.model)).strip() or default.model,
        num_ctx=_bounded_int(raw.get("num_ctx"), default.num_ctx, 4096, 131072),
        text_max_tokens=_bounded_int(
            raw.get("text_max_tokens"), default.text_max_tokens, 128, 32768
        ),
        image_max_tokens=_bounded_int(
            raw.get("image_max_tokens"), default.image_max_tokens, 128, 32768
        ),
        text_temperature=_bounded_float(
            raw.get("text_temperature"), default.text_temperature, 0.0, 1.2
        ),
        image_temperature=_bounded_float(
            raw.get("image_temperature"), default.image_temperature, 0.0, 1.2
        ),
        direct_vision=bool(raw.get("direct_vision", default.direct_vision)),
        knowledge_base=bool(raw.get("knowledge_base", default.knowledge_base)),
        remote_api_url=str(raw.get("remote_api_url", default.remote_api_url)).strip(),
        remote_model=str(raw.get("remote_model", default.remote_model)).strip(),
        remote_api_key_env=(
            str(raw.get("remote_api_key_env", default.remote_api_key_env)).strip()
            or default.remote_api_key_env
        ),
    )


def load_mode_profiles() -> dict[str, ModeProfile]:
    loaded: dict[str, Any] = {}
    if CONFIG_PATH.exists():
        try:
            value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                loaded = value
        except (OSError, ValueError, TypeError):
            loaded = {}

    profiles = {
        mode: _merge_profile(default, loaded.get(mode))
        for mode, default in DEFAULTS.items()
    }

    expert = profiles["expert"]
    env_url = os.environ.get("YANBO_EXPERT_API_URL", "").strip()
    env_model = os.environ.get("YANBO_EXPERT_MODEL", "").strip()
    env_local_model = os.environ.get("YANBO_EXPERT_LOCAL_MODEL", "").strip()
    if env_url:
        expert = replace(expert, remote_api_url=env_url)
    if env_model:
        expert = replace(expert, remote_model=env_model)
    if env_local_model:
        expert = replace(expert, model=env_local_model)
    profiles["expert"] = expert
    return profiles
