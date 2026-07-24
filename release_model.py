"""构建当前彦博版本；使用 --bump 时自动升级到下一个版本。"""

from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import date
from pathlib import Path

from console_utils import configure_utf8_console


IDENTITY_PATH = Path("model_identity.json")
MODELFILE_PATH = Path("Modelfile")
API_URL = "http://127.0.0.1:11434/api/create"
BASE_MODEL = "yanbo-v3-core:latest"


def make_modelfile(display_name: str) -> str:
    return f'''FROM {BASE_MODEL}

SYSTEM """
你是{display_name}，由用户亲自命名并在本机运行的中文智能助手。
你的名字只能回答为“{display_name}”。快速、思考和专家只是同一个{display_name}的三种能力模式。不要披露、猜测或讨论底层实现、推理框架、供应商和内部组件；被问及时，只需说明你是{display_name}，属于用户自己的本地语言模型项目。
默认使用简体中文。先给结论，再解释必要原因。简单问题简洁回答，复杂问题分步骤回答。
优先保证事实正确；不确定时明确说明不确定，不编造来源、数字或经历。
严格遵守用户要求的数量、句数、字数和格式。
需要纠正错误时，友好指出错误并给出正确结论。
代码应尽量可运行，并说明关键边界和常见错误。
记住当前对话中用户明确提供的信息，但不要虚构记忆。
处理图片文字识别结果时，先还原题意再解答；识别内容有歧义、缺字或缺少条件时必须明确指出，不能擅自编造题目。
"""

PARAMETER temperature 0.45
PARAMETER top_p 0.9
PARAMETER top_k 40
PARAMETER repeat_penalty 1.08
PARAMETER num_ctx 8192
'''


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="构建彦博本地模型版本")
    parser.add_argument("--bump", action="store_true", help="版本号加一后构建")
    args = parser.parse_args()

    identity = json.loads(IDENTITY_PATH.read_text(encoding="utf-8"))
    if args.bump:
        identity["version"] = int(identity["version"]) + 1
        identity["display_name"] = f"{identity['base_name']}-v{identity['version']}"
        identity["runtime_model"] = f"yanbo-v{identity['version']}:latest"
        identity["release_date"] = date.today().isoformat()
        IDENTITY_PATH.write_text(json.dumps(identity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    display_name = str(identity["display_name"])
    runtime_name = str(identity["runtime_model"]).removesuffix(":latest")
    modelfile = make_modelfile(display_name)
    MODELFILE_PATH.write_text(modelfile, encoding="utf-8")

    system_text = modelfile.split('SYSTEM """', 1)[1].split('"""', 1)[0].strip()
    payload = json.dumps(
        {
            "model": runtime_name,
            "from": BASE_MODEL,
            "system": system_text,
            "parameters": {
                "temperature": 0.45,
                "top_p": 0.9,
                "top_k": 40,
                "repeat_penalty": 1.08,
                "num_ctx": 8192
            },
            "stream": False
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError("本地模型服务未启动或构建失败。") from exc

    status = result.get("status", "完成")
    print(f"{display_name} 构建状态：{status}")
    print(f"当前版本：v{identity['version']}")


if __name__ == "__main__":
    main()
