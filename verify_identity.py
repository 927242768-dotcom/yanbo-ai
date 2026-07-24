"""检查彦博-v3身份、三模式模型配置和仓库公开文本的一致性。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from console_utils import configure_utf8_console


ROOT = Path(__file__).resolve().parent
IDENTITY_NAME = "彦博-v3"
RUNTIME_MODEL = "yanbo-v3:latest"


def _decoded_terms() -> tuple[str, ...]:
    encoded = (
        (81, 119, 101, 110),
        (103, 112, 116, 45, 111, 115, 115),
        (103, 101, 109, 109, 97),
    )
    return tuple("".join(chr(code) for code in value) for value in encoded)


def _tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / value.decode("utf-8") for value in result.stdout.split(b"\0") if value]


def _check_public_text() -> list[str]:
    failures: list[str] = []
    blocked = tuple(value.lower() for value in _decoded_terms())
    ignored_suffixes = {
        ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".ico",
        ".apk", ".aab", ".zip", ".safetensors", ".jar",
    }
    for path in _tracked_files():
        if path.suffix.lower() in ignored_suffixes or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lowered = text.lower()
        for term in blocked:
            if term in lowered:
                failures.append(f"{path.relative_to(ROOT)} 包含不允许公开的模型名称")
                break
    return failures


def _check_identity_files() -> list[str]:
    failures: list[str] = []
    identity = json.loads((ROOT / "model_identity.json").read_text(encoding="utf-8"))
    if identity.get("display_name") != IDENTITY_NAME:
        failures.append("model_identity.json 的display_name不是彦博-v3")
    if identity.get("runtime_model") != RUNTIME_MODEL:
        failures.append("model_identity.json 的runtime_model不是yanbo-v3:latest")

    profiles = json.loads((ROOT / "capability_config.json").read_text(encoding="utf-8"))
    expected_names = {
        "fast": "彦博-快速",
        "thinking": "彦博-思考",
        "expert": "彦博-专家",
    }
    for mode, display_name in expected_names.items():
        profile = profiles.get(mode, {})
        if profile.get("display_name") != display_name:
            failures.append(f"{mode}模式名称不正确")
        if profile.get("model") != RUNTIME_MODEL:
            failures.append(f"{mode}模式没有使用统一的彦博-v3运行模型")
        if profile.get("backend") != "native":
            failures.append(f"{mode}模式没有锁定本地彦博-v3后端")
    return failures


def main() -> None:
    configure_utf8_console()
    failures = _check_identity_files() + _check_public_text()
    if failures:
        for failure in failures:
            print(f"[失败] {failure}")
        raise SystemExit(1)
    print("[通过] 彦博-v3身份统一检查")
    print("[通过] 彦博-快速、彦博-思考、彦博-专家均使用yanbo-v3:latest")
    print("[通过] Git公开文本未发现外部模型品牌")


if __name__ == "__main__":
    main()
