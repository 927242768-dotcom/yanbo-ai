"""彦博图片识别与做题能力回归测试。"""

from __future__ import annotations

import argparse
import io
import time

from PIL import Image, ImageDraw, ImageFont

from assistant_engine import AssistantEngine, DISPLAY_NAME
from console_utils import configure_utf8_console
from image_understanding import ImageTextRecognizer


def make_image(lines: list[str], font_size: int = 58) -> bytes:
    font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", font_size)
    width = 1300
    line_height = font_size + 32
    height = max(260, 50 + line_height * len(lines))
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    y = 35
    for line in lines:
        draw.text((45, y), line, font=font, fill="black")
        y += line_height
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description=f"测试 {DISPLAY_NAME} 图片做题能力")
    parser.add_argument("--mode", choices=["auto", "native", "fallback"], default="auto")
    args = parser.parse_args()

    recognizer = ImageTextRecognizer()
    ocr_cases = [
        (["题目：17 + 25 = ?"], ["17", "25"]),
        (["小明有17个苹果，又买了25个苹果。", "现在一共有多少个苹果？"], ["17", "25", "苹果"]),
    ]

    passed = 0
    print("=== 图片文字识别测试 ===")
    for lines, keywords in ocr_cases:
        image_bytes = make_image(lines)
        started = time.perf_counter()
        result = recognizer.recognize_bytes(image_bytes)
        elapsed = time.perf_counter() - started
        ok = all(keyword in result.text for keyword in keywords)
        passed += int(ok)
        print(f"[{'通过' if ok else '失败'}] 置信度：{result.confidence:.0%}，耗时：{elapsed:.2f}秒")
        print(result.text + "\n")
    print(f"文字识别：{passed}/{len(ocr_cases)} 通过\n")

    print("=== 图片做题端到端测试 ===")
    engine = AssistantEngine(backend=args.mode)
    image_bytes = make_image(["请计算：17 + 25 = ?"])
    started = time.perf_counter()
    answer = engine.image_reply(
        image_bytes,
        user_text="识别题目并给出计算过程和答案。",
        filename="测试题.png",
        max_new_tokens=180,
        temperature=0.0,
    )
    elapsed = time.perf_counter() - started
    ok = "42" in answer
    print(f"[{'通过' if ok else '失败'}] 耗时：{elapsed:.2f}秒")
    print(answer)
    print(f"\n图片做题：{'通过' if ok else '失败'}")
    if passed != len(ocr_cases) or not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
