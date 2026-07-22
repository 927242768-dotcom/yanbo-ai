"""评估主力模型的数据联动、指令遵循和短任务响应质量。"""

from __future__ import annotations

import argparse
import re
import time

from assistant_engine import AssistantEngine, DISPLAY_NAME
from behavior_examples import BehaviorExampleLibrary
from console_utils import configure_utf8_console
from response_contract import analyze_response_contract, enforce_response_contract
from training_quality import is_training_answer_usable


def _list_item_count(text: str) -> int:
    return len(re.findall(r"(?m)^\s*\d+[.、)）]\s*", text))


def _sentence_count(text: str) -> int:
    return len(re.findall(r"[^。！？!?]+[。！？!?]", text))


def _report(name: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'通过' if ok else '失败'}] {name}{'：' + detail if detail else ''}")
    return ok


def run_static_checks() -> tuple[int, int]:
    passed = 0
    total = 0

    contract = analyze_response_contract("请只给三个减少拖延的办法。")
    total += 1
    passed += _report(
        "数量硬约束解析",
        contract.exact_items == 3 and contract.requires_buffering and not contract.allow_continuation,
    )

    contract = analyze_response_contract("为什么天空是蓝色的？请用两句话解释。")
    total += 1
    passed += _report(
        "句数硬约束解析",
        contract.exact_sentences == 2 and contract.max_new_tokens is not None,
    )

    sample = "下面给你四条：\n1. 第一条。\n2. 第二条。\n3. 第三条。\n4. 多余内容。\n总结。"
    contract = analyze_response_contract("只给三条建议。")
    fixed = enforce_response_contract(sample, contract)
    total += 1
    passed += _report(
        "生成后数量校正",
        _list_item_count(fixed) == 3 and "多余内容" not in fixed and "总结" not in fixed,
        fixed.replace("\n", " / "),
    )

    library = BehaviorExampleLibrary()
    examples = library.retrieve("写一个Python函数计算非负整数阶乘，负数要报错。")
    total += 1
    passed += _report(
        "训练数据联动主力模型",
        bool(examples) and "factorial" in examples[0].assistant and "ValueError" in examples[0].assistant,
    )

    total += 1
    passed += _report(
        "截断导师答案拦截",
        not is_training_answer_usable("```python\ndef broken():\n    return 1"),
    )
    return passed, total


def run_model_checks(mode: str) -> tuple[int, int]:
    engine = AssistantEngine(backend=mode)
    cases = [
        (
            "礼貌改写直接输出",
            "把这句话改得更礼貌：你赶紧把文件发给我。",
            lambda answer: len(answer) <= 80
            and "文件" in answer
            and not any(word in answer for word in ("推荐", "版本", "总结", "修改理由")),
        ),
        (
            "严格输出三项",
            "请只给三个减少拖延的办法。",
            lambda answer: _list_item_count(answer) == 3
            and not re.search(r"(?m)^\s*4[.、)）]", answer),
        ),
        (
            "严格输出两句话",
            "请用两句话解释为什么声音不能在真空中传播。",
            lambda answer: _sentence_count(answer) == 2 and "介质" in answer and "真空" in answer,
        ),
        (
            "相似训练样本辅助代码",
            "写一个Python函数计算非负整数阶乘，负数要报错。",
            lambda answer: all(word in answer for word in ("def", "factorial", "ValueError", "return")),
        ),
    ]

    passed = 0
    times: list[float] = []
    for name, prompt, validator in cases:
        engine.reset()
        started = time.perf_counter()
        answer = engine.reply(prompt, max_new_tokens=700, temperature=0.0)
        elapsed = time.perf_counter() - started
        times.append(elapsed)
        ok = bool(answer.strip()) and validator(answer)
        passed += _report(name, ok, f"{elapsed:.2f}秒，{len(answer)}字")
        print(answer + "\n")
    print(f"模型检查平均耗时：{sum(times) / max(1, len(times)):.2f}秒/题")
    return passed, len(cases)


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description=f"评估{DISPLAY_NAME}性能升级")
    parser.add_argument("--mode", choices=["auto", "native", "fallback"], default="auto")
    parser.add_argument("--full", action="store_true", help="运行真实模型生成检查")
    args = parser.parse_args()

    passed, total = run_static_checks()
    if args.full:
        model_passed, model_total = run_model_checks(args.mode)
        passed += model_passed
        total += model_total
    print(f"\n模型升级评估：{passed}/{total} 通过")
    raise SystemExit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
