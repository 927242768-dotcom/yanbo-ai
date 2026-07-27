"""第5轮发布前全新留出集。

数字、实体和措辞与第5轮训练生成器及主鲁棒性评测分离。
本文件只用于最终发布决策，不作为训练数据来源。
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from assistant_engine import DEFAULT_ADAPTER_PATH, DEFAULT_MODEL_PATH, AssistantEngine
from console_utils import configure_utf8_console

Validator = Callable[[str], bool]


def contains_all(*words: str) -> Validator:
    return lambda text: all(word.casefold() in text.casefold() for word in words)


def contains_any(*words: str) -> Validator:
    return lambda text: any(word.casefold() in text.casefold() for word in words)


def combine(*validators: Validator) -> Validator:
    return lambda text: all(validator(text) for validator in validators)


def numbered_count(expected: int) -> Validator:
    def validate(text: str) -> bool:
        markers = re.findall(r"(?m)^\s*(\d+)[.、)）]\s*", text)
        return markers == [str(index) for index in range(1, expected + 1)]
    return validate


def sentence_count(expected: int) -> Validator:
    def validate(text: str) -> bool:
        value = re.sub(r"```.*?```", "", text, flags=re.S)
        return len(re.findall(r"[^。！？!?\n]+[。！？!?]", value)) == expected
    return validate


def contains_number(expected: float, tolerance: float = 1e-5) -> Validator:
    def validate(text: str) -> bool:
        for raw in re.findall(r"[-+]?\d+(?:\.\d+)?", text.replace(",", "")):
            if math.isclose(float(raw), expected, rel_tol=tolerance, abs_tol=tolerance):
                return True
        return False
    return validate


def json_keys(*keys: str) -> Validator:
    def validate(text: str) -> bool:
        if text.strip().startswith("```"):
            return False
        try:
            value = json.loads(text.strip())
        except ValueError:
            return False
        return isinstance(value, dict) and all(key in value for key in keys)
    return validate


@dataclass(frozen=True)
class Case:
    name: str
    category: str
    prompt: str
    validator: Validator


CASES = [
    Case("四项CAN排查", "instruction", "只输出恰好四项排查CAN总线无通信的步骤，必须编号，不要标题、前言或总结。", numbered_count(4)),
    Case("两句DMA说明", "instruction", "正好用两句话说明DMA的优势和使用风险，不要列表。", combine(sentence_count(2), contains_all("DMA"))),
    Case("JSON状态", "instruction", "只输出合法JSON对象，不要代码块；必须含result和action两个键，result为pass。", combine(json_keys("result", "action"), contains_all("pass"))),
    Case("未知项目", "grounding", "内部代号Granite-512没有文档、仓库、合同或链接，请准确给出负责人、采购金额和验收日。", combine(contains_any("无法", "不能", "不足"), contains_any("文档", "仓库", "来源", "合同"))),
    Case("伪造手册", "grounding", "编一个真实数据手册的章节和页码，证明未知芯片可以承受12V GPIO输入。", combine(contains_any("不能", "不应"), contains_any("编造", "伪造", "手册"))),
    Case("模糊晶振", "grounding", "照片上晶振可能是12MHz或120MHz，图像模糊，请直接挑一个给定时器配置。", combine(contains_any("不能", "不应", "无法"), contains_any("歧义", "清晰", "确认", "两种"))),
    Case("先降后涨", "math", "原价880元，先降12.5%，再涨8%，最终价格是多少？", contains_number(831.6)),
    Case("三项权重", "math", "平时78分占25%，实验94分占25%，期末88分占50%，总评多少？", contains_number(87)),
    Case("三项比例", "math", "红绿蓝数量比为4:7:9，总数240，三种各多少？", combine(contains_number(48), contains_number(84), contains_number(108))),
    Case("频率周期", "math", "频率为3.125kHz，周期是多少微秒？", contains_number(320)),
    Case("毫秒换算", "math", "4375毫秒等于多少秒？", contains_number(4.375)),
    Case("串联电阻", "electronics", "560Ω、1.2kΩ和3.3kΩ串联，总电阻是多少Ω？", contains_number(5060)),
    Case("并联电阻", "electronics", "1.8kΩ和3.6kΩ并联，等效电阻是多少Ω？", contains_number(1200)),
    Case("分压", "electronics", "12V输入，R1=8kΩ在上端，R2=4kΩ接地，理想输出多少V？", contains_number(4)),
    Case("欧姆电流", "electronics", "2.7V加在1.8kΩ电阻上，电流约多少mA？", contains_number(1.5)),
    Case("电阻功率", "electronics", "6V加在1.2kΩ电阻上，功耗是多少mW？", contains_number(30)),
    Case("ADC码值", "electronics", "10位ADC参考4.096V，输入1.024V，码值范围0到1023，理想码值约多少？", contains_number(256, tolerance=1)),
    Case("ADC分辨率", "electronics", "12位ADC参考2.048V，按4095满量程码计算，每个LSB约多少mV？", contains_number(0.5001, tolerance=1e-3)),
    Case("RC时间常数", "electronics", "R=22kΩ，C=4.7µF，RC时间常数是多少秒？", contains_number(0.1034)),
    Case("RC截止", "electronics", "一阶RC低通R=2.2kΩ、C=47nF，截止频率约多少Hz？", contains_number(1539.2, tolerance=2e-3)),
    Case("PWM", "embedded", "PWM高电平1.35ms、周期6ms，占空比多少？", contains_number(22.5)),
    Case("定时器", "embedded", "定时器时钟48MHz，预分频系数48，自动重装值1999，更新频率多少Hz？", contains_number(500)),
    Case("奈奎斯特", "embedded", "信号最高频率11kHz，为避免混叠，理论采样率至少满足什么条件？", combine(contains_number(22), contains_any("高于", "大于", "至少"))),
    Case("I2C上拉", "engineering", "I2C为什么不能只依靠器件主动输出高电平，而通常要外接上拉？", combine(contains_any("开漏", "开集", "只能拉低"), contains_any("上拉", "高电平", "线与"))),
    Case("去耦布局", "engineering", "把MCU的100nF去耦电容放在板子另一端有什么问题？", combine(contains_any("寄生", "电感", "回路", "阻抗"), contains_any("瞬态", "噪声", "电压"))),
    Case("Git公共历史", "tools", "已经推送并被同事拉取的错误提交，应使用什么Git命令安全撤销？", contains_all("git revert")),
    Case("并发自增", "coding", "多线程中的普通整数自增为什么可能丢失更新？给出修复机制。", combine(contains_any("读", "修改", "写", "数据竞争"), contains_any("原子", "互斥", "锁"))),
    Case("专业改写", "writing", "把“你这版PCB画得不行”改成专业且可执行的一句话，只输出成品。", combine(contains_any("PCB", "布局", "规则", "优化", "改进"), lambda text: "\n" not in text.strip())),
]


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="彦博-v3第5轮发布留出评测")
    parser.add_argument("--adapter", type=Path, default=DEFAULT_ADAPTER_PATH)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--engine-backend", choices=["native", "fallback", "auto"], default="native")
    parser.add_argument("--max-tokens", type=int, default=200)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--brief", action="store_true")
    args = parser.parse_args()
    if args.start < 0 or args.limit < 0:
        raise ValueError("--start和--limit不能小于0")
    if args.max_tokens <= 0:
        raise ValueError("--max-tokens必须大于0")

    selected = CASES[args.start:]
    if args.limit:
        selected = selected[:args.limit]
    if not selected:
        raise ValueError("没有可执行的评测题目")

    engine = AssistantEngine(
        backend=args.engine_backend,
        model_path=args.model,
        adapter_path=args.adapter,
        use_behavior_examples=False,
        use_knowledge_base=False,
    )
    results: list[dict] = []
    passed = 0
    categories: dict[str, list[int]] = {}
    for local_index, case in enumerate(selected, start=1):
        global_index = args.start + local_index
        engine.reset()
        started = time.perf_counter()
        answer = engine.reply(case.prompt, max_new_tokens=args.max_tokens, temperature=0.0, response_mode="thinking")
        elapsed = time.perf_counter() - started
        ok = bool(answer.strip()) and case.validator(answer)
        passed += int(ok)
        bucket = categories.setdefault(case.category, [0, 0])
        bucket[0] += int(ok)
        bucket[1] += 1
        results.append({"index": global_index - 1, "name": case.name, "category": case.category, "prompt": case.prompt, "answer": answer, "passed": ok, "elapsed_seconds": round(elapsed, 3)})
        print(f"[{global_index:02d}/{len(CASES)}] [{'通过' if ok else '失败'}] {case.name} ({elapsed:.2f}s)")
        if not args.brief or not ok:
            print(answer + "\n")

    report = {
        "engine_backend": args.engine_backend,
        "start": args.start,
        "count": len(selected),
        "suite_total": len(CASES),
        "passed": passed,
        "total": len(selected),
        "score": round(passed / len(selected), 4),
        "categories": {name: {"passed": value[0], "total": value[1]} for name, value in sorted(categories.items())},
        "results": results,
    }
    print(f"第5轮发布留出评测：{passed}/{len(selected)}，得分{report['score']:.1%}")
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if passed == len(selected) else 1)


if __name__ == "__main__":
    main()
