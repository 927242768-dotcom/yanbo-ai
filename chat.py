"""彦博命令行聊天入口，支持文字与图片题目流式输出。"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from assistant_engine import AssistantEngine, DISPLAY_NAME
from console_utils import configure_utf8_console


IMAGE_COMMAND = re.compile(
    r'^/(?:image|img|图片)\s+(?:"([^"]+)"|(\S+))(?:\s+(.*))?$',
    flags=re.IGNORECASE,
)


def print_stream(prefix: str, chunks) -> None:
    print(prefix, end="", flush=True)
    for chunk in chunks:
        print(chunk, end="", flush=True)
    print()


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description=f"与 {DISPLAY_NAME} 聊天")
    parser.add_argument("--mode", choices=["auto", "native", "fallback"], default="auto")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    args = parser.parse_args()

    print(f"正在启动 {DISPLAY_NAME}……")
    engine = AssistantEngine(backend=args.mode, device=args.device)
    print(f"{engine.backend_info} 已启动。")
    print("输入 /image 图片路径 可识别图片做题；输入 /reset 清空上下文；输入 /exit 退出。")
    print('路径包含空格时示例：/image "D:\\作业图片\\题目1.png" 请详细解答')

    while True:
        try:
            user_text = input("\n你：").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DISPLAY_NAME}：再见！")
            break

        if user_text.lower() in {"/exit", "exit", "quit", "退出"}:
            print(f"{DISPLAY_NAME}：再见！")
            break
        if user_text.lower() in {"/reset", "reset", "清空"}:
            engine.reset()
            print(f"{DISPLAY_NAME}：上下文已清空。")
            continue
        if user_text.lower() in {"/help", "help", "帮助"}:
            print("命令：")
            print("  /image 图片路径 [要求]  识别并解答图片题目")
            print("  /reset                 清空上下文")
            print("  /exit                  退出")
            continue

        image_match = IMAGE_COMMAND.match(user_text)
        if image_match:
            image_path = Path(image_match.group(1) or image_match.group(2)).expanduser()
            request = (image_match.group(3) or "请识别并详细解答图片中的题目。").strip()
            if not image_path.is_file():
                print(f"{DISPLAY_NAME}：没有找到图片：{image_path}")
                continue
            try:
                image_bytes = image_path.read_bytes()
                print(f"{DISPLAY_NAME}：正在识别图片文字……", flush=True)
                result = engine.recognize_image(image_bytes)
                print(
                    f"识别完成，共{len(result.lines)}行，"
                    f"平均置信度{result.confidence:.0%}。正在解题……"
                )
                print_stream(
                    f"{DISPLAY_NAME}：",
                    engine.stream_image_reply(
                        image_bytes=image_bytes,
                        user_text=request,
                        filename=image_path.name,
                        ocr_result=result,
                    ),
                )
            except Exception as exc:
                print(f"{DISPLAY_NAME}：图片处理失败：{exc}")
            continue

        print_stream(f"{DISPLAY_NAME}：", engine.stream_reply(user_text))


if __name__ == "__main__":
    main()
