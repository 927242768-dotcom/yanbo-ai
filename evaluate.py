"""彦博当前版本的基础能力与回归测试。"""

from __future__ import annotations

import argparse
import re
import time

from assistant_engine import AssistantEngine, DISPLAY_NAME, try_calculate
from console_utils import configure_utf8_console


MATH_CASES = {
    "1+2": "3",
    "计算 12*8": "96",
    "(5+3)*4等于多少？": "32",
    "100除以4是多少": "25",
    "-7加12": "5",
    "7/2": "3.5",
    "2的平方是多少": "4",
}

QUALITY_CASES = [
    ("你叫什么名字？", [DISPLAY_NAME]),
    ("为什么天空通常是蓝色的？请用两句话解释。", ["波长", "散射"]),
    ("Python 中列表和元组最核心的区别是什么？", ["列表", "可变", "元组", "不可变"]),
    ("我说今天是星期八，你应该直接相信吗？", ["不", "七"]),
    ("把这句话改得更礼貌：你赶紧把文件发给我。", ["请", "文件"]),
    ("请只给三个减少拖延的办法。", ["1", "2", "3"]),
]

ADVANCED_CASES = [
    ("解方程：3x+5=20。", ["x", "5"]),
    ("一件100元商品先涨价20%，再降价20%，最后多少钱，是否回到原价？", ["96", "不"]),
    ("写一个Python函数计算非负整数阶乘，负数要报错。", ["def", "factorial", "ValueError", "return"]),
    ("这段Python代码有什么语法错误：for i in range(3) print(i)", ["冒号", "for"]),
    ("写一条SQL，统计employees表中每个department_id的员工人数。", ["SELECT", "COUNT", "GROUP BY"]),
    ("为什么相关性不能直接证明因果关系？", ["因果", "不能"]),
]


def contains_all(text: str, words: list[str]) -> bool:
    return all(word.lower() in text.lower() for word in words)


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description=f"评估 {DISPLAY_NAME}")
    parser.add_argument("--mode", choices=["auto", "native", "fallback"], default="auto")
    parser.add_argument("--full", action="store_true", help="运行较慢的完整生成测试")
    parser.add_argument("--advanced-only", action="store_true", help="只运行做题与代码测试")
    args = parser.parse_args()

    passed = 0
    print("=== 数学工具测试 ===")
    for question, expected in MATH_CASES.items():
        answer = try_calculate(question)
        ok = answer is not None and re.search(rf"=\s*{re.escape(expected)}。", answer) is not None
        passed += int(ok)
        print(f"[{'通过' if ok else '失败'}] {question} -> {answer}")
    print(f"数学测试：{passed}/{len(MATH_CASES)} 通过\n")

    print(f"正在启动 {DISPLAY_NAME}……")
    started = time.perf_counter()
    engine = AssistantEngine(backend=args.mode)
    print(f"当前模型：{engine.backend_info}")
    print(f"启动耗时：{time.perf_counter() - started:.2f} 秒\n")

    identity_answer = engine.reply("你叫什么名字？", max_new_tokens=64, temperature=0.0)
    identity_ok = DISPLAY_NAME in identity_answer
    print(f"身份测试：[{'通过' if identity_ok else '失败'}] {identity_answer}")

    hidden_name = "".join(chr(code) for code in (79, 108, 108, 97, 109, 97))
    privacy_ok = hidden_name.lower() not in identity_answer.lower()
    print(f"展示隔离：[{'通过' if privacy_ok else '失败'}]")

    engine.reset()
    first = engine.reply("我叫小林，正在学习 Python。", max_new_tokens=96, temperature=0.0)
    second = engine.reply("我刚才说我叫什么、在学什么？", max_new_tokens=96, temperature=0.0)
    memory_ok = "小林" in second and "Python" in second
    print(f"多轮记忆：[{'通过' if memory_ok else '失败'}] {second}\n")

    if args.advanced_only:
        print("=== 做题与代码能力测试 ===")
        advanced_passed = 0
        times: list[float] = []
        for prompt, keywords in ADVANCED_CASES:
            engine.reset()
            started = time.perf_counter()
            answer = engine.reply(prompt, max_new_tokens=220, temperature=0.0)
            elapsed = time.perf_counter() - started
            times.append(elapsed)
            ok = contains_all(answer, keywords)
            advanced_passed += int(ok)
            print(f"[{'通过' if ok else '失败'}] 问：{prompt}")
            print(f"答：{answer}\n耗时：{elapsed:.2f} 秒\n")
        print(f"做题与代码：{advanced_passed}/{len(ADVANCED_CASES)} 通过")
        print(f"平均生成耗时：{sum(times) / max(1, len(times)):.2f} 秒/题")
        return

    if not args.full:
        print("基础回归测试完成。添加 --full 可运行完整质量测试。")
        return

    print("=== 完整质量测试 ===")
    quality_passed = 0
    times: list[float] = []
    for prompt, keywords in QUALITY_CASES:
        engine.reset()
        started = time.perf_counter()
        answer = engine.reply(prompt, max_new_tokens=220, temperature=0.0)
        elapsed = time.perf_counter() - started
        times.append(elapsed)
        ok = contains_all(answer, keywords)
        quality_passed += int(ok)
        print(f"[{'通过' if ok else '失败'}] 问：{prompt}")
        print(f"答：{answer}\n耗时：{elapsed:.2f} 秒\n")

    print(f"基础质量测试：{quality_passed}/{len(QUALITY_CASES)} 通过")

    print("\n=== 做题与代码能力测试 ===")
    advanced_passed = 0
    for prompt, keywords in ADVANCED_CASES:
        engine.reset()
        started = time.perf_counter()
        answer = engine.reply(prompt, max_new_tokens=220, temperature=0.0)
        elapsed = time.perf_counter() - started
        times.append(elapsed)
        ok = contains_all(answer, keywords)
        advanced_passed += int(ok)
        print(f"[{'通过' if ok else '失败'}] 问：{prompt}")
        print(f"答：{answer}\n耗时：{elapsed:.2f} 秒\n")

    total_passed = quality_passed + advanced_passed
    total_cases = len(QUALITY_CASES) + len(ADVANCED_CASES)
    print(f"综合质量测试：{total_passed}/{total_cases} 通过")
    print(f"其中做题与代码：{advanced_passed}/{len(ADVANCED_CASES)} 通过")
    print(f"平均生成耗时：{sum(times) / max(1, len(times)):.2f} 秒/题")


if __name__ == "__main__":
    main()
