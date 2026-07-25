"""独立评估彦博-v3兼容模型训练前后的真实生成质量。"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from assistant_engine import (
    DEFAULT_ADAPTER_PATH,
    DEFAULT_MODEL_PATH,
    SYSTEM_PROMPT,
    AssistantEngine,
    FallbackBackend,
)
from console_utils import configure_utf8_console


Validator = Callable[[str], bool]


def contains_all(*words: str) -> Validator:
    return lambda text: all(word.casefold() in text.casefold() for word in words)


def contains_any(*words: str) -> Validator:
    return lambda text: any(word.casefold() in text.casefold() for word in words)


def numbered_count(expected: int) -> Validator:
    def validate(text: str) -> bool:
        matches = re.findall(r"(?m)^\s*\d+[.、)）]\s*", text)
        return len(matches) == expected and not re.search(
            rf"(?m)^\s*{expected + 1}[.、)）]\s*", text
        )
    return validate


def sentence_count(expected: int, *words: str) -> Validator:
    def validate(text: str) -> bool:
        sentences = re.findall(r"[^。！？!?]+[。！？!?]", text)
        return len(sentences) == expected and all(word in text for word in words)
    return validate


def combine(*validators: Validator) -> Validator:
    return lambda text: all(validator(text) for validator in validators)


@dataclass(frozen=True)
class Case:
    name: str
    category: str
    prompt: str
    validator: Validator


CASES = [
    Case(
        "严格两项输出",
        "instruction",
        "只给两个排查程序卡死的步骤，不要前言、解释和总结。",
        numbered_count(2),
    ),
    Case(
        "严格三句话",
        "instruction",
        "请用三句话说明训练集、验证集和测试集各自的作用。",
        sentence_count(3, "训练", "验证", "测试"),
    ),
    Case(
        "礼貌改写成品",
        "writing",
        "把‘你怎么还没把测试文件发来’改得礼貌专业，只输出改写后的句子。",
        lambda text: len(text) <= 90 and "测试" in text and "文件" in text
        and not any(word in text for word in ("改写", "版本", "说明", "理由")),
    ),
    Case(
        "信息不足不编造",
        "grounding",
        "项目代号是BlueFox。请告诉我它准确的负责人、发布日期和预算。",
        combine(contains_any("不足", "没有", "未提供", "无法确定", "不能确定"), contains_any("资料", "信息", "文档", "来源")),
    ),
    Case(
        "相关不等于因果",
        "logic",
        "某城市雨伞销量和交通事故都上升，能直接证明买雨伞导致事故吗？",
        combine(contains_any("不能", "不可以"), contains_any("相关", "共同", "混杂", "第三")),
    ),
    Case(
        "肯定后件识别",
        "logic",
        "如果服务器宕机，网站会打不开。现在网站打不开，能必然推出服务器宕机吗？",
        combine(contains_any("不能", "不一定"), contains_any("其他", "网络", "域名", "故障", "原因")),
    ),
    Case(
        "逆向两步代数",
        "math",
        "一个数减去4以后再乘3等于27，这个数是多少？写出必要步骤。",
        contains_all("13"),
    ),
    Case(
        "比例分配",
        "math",
        "红球和蓝球数量比为3:5，一共有40个球，两种球各有多少个？",
        contains_all("15", "25"),
    ),
    Case(
        "缺失平均数",
        "math",
        "五个数平均为12，其中四个数是8、10、13、14，第五个数是多少？",
        contains_all("15"),
    ),
    Case(
        "Python空输入边界",
        "coding",
        "写一个Python函数求数值列表平均值；空列表必须抛出ValueError。",
        contains_all("def", "ValueError", "sum", "len"),
    ),
    Case(
        "Python默认参数修复",
        "coding",
        "修复这个函数的共享默认列表问题：def collect(x, items=[]): items.append(x); return items",
        contains_all("None", "items", "append"),
    ),
    Case(
        "C缓冲区安全",
        "coding",
        "C语言拼接格式化字符串时，怎样降低sprintf造成缓冲区溢出的风险？",
        combine(contains_all("snprintf"), contains_any("大小", "长度", "容量", "返回值")),
    ),
    Case(
        "Git取消暂存",
        "tools",
        "README.md已经git add，但我想保留修改并取消暂存，命令是什么？",
        contains_all("git restore --staged", "README.md"),
    ),
    Case(
        "SQL保留零员工部门",
        "coding",
        "写SQL统计每个部门的员工数，部门表departments，员工表employees，并保留员工数为0的部门。",
        combine(contains_all("LEFT JOIN", "COUNT", "GROUP BY"), contains_any("employee_id", "员工")),
    ),
    Case(
        "复杂度判断",
        "coding",
        "外层循环n次，内层每次也循环n次，循环体是常数操作，时间复杂度是什么？说明一句原因。",
        contains_any("O(n²)", "O(n^2)", "O(n * n)", "O(n*n)"),
    ),
    Case(
        "OCR关键歧义",
        "vision_reasoning",
        "图片中的电阻值可能是1kΩ也可能是7kΩ，两种结果不同。现在图片看不清，请直接选一个计算。",
        combine(contains_any("不能", "无法", "不应"), contains_any("清晰", "确认", "歧义", "重新")),
    ),
    Case(
        "FPGA跨时钟域",
        "engineering",
        "为什么单比特控制信号跨时钟域时常用两级触发器同步？它不适合直接解决什么问题？",
        combine(contains_all("亚稳"), contains_any("多比特", "总线", "脉冲")),
    ),
    Case(
        "测试不能证明无Bug",
        "engineering",
        "一个程序连续通过了100次测试，能证明它以后绝对没有Bug吗？",
        combine(contains_any("不能", "不可以"), contains_any("覆盖", "输入", "路径", "边界")),
    ),
]


def generate_raw(adapter: Path, prompt: str, max_tokens: int) -> str:
    backend = FallbackBackend(
        model_path=DEFAULT_MODEL_PATH,
        adapter_path=adapter,
        device="auto",
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    return backend.generate(messages, max_new_tokens=max_tokens, temperature=0.0)


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="评估兼容模型训练升级")
    parser.add_argument("--adapter", type=Path, default=DEFAULT_ADAPTER_PATH)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--execution", choices=["raw", "engine"], default="raw")
    parser.add_argument("--max-tokens", type=int, default=220)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--brief", action="store_true")
    args = parser.parse_args()

    if not args.adapter.exists():
        raise FileNotFoundError(f"适配器不存在：{args.adapter}")

    engine: AssistantEngine | None = None
    backend: FallbackBackend | None = None
    if args.execution == "engine":
        engine = AssistantEngine(
            backend="fallback",
            model_path=args.model,
            adapter_path=args.adapter,
            use_behavior_examples=False,
            use_knowledge_base=False,
        )
    else:
        backend = FallbackBackend(
            model_path=args.model,
            adapter_path=args.adapter,
            device="auto",
        )

    results = []
    passed = 0
    category_totals: dict[str, list[int]] = {}
    for index, case in enumerate(CASES, start=1):
        started = time.perf_counter()
        if engine is not None:
            engine.reset()
            answer = engine.reply(
                case.prompt,
                max_new_tokens=args.max_tokens,
                temperature=0.0,
                response_mode="thinking",
            )
        else:
            assert backend is not None
            answer = backend.generate(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": case.prompt},
                ],
                max_new_tokens=args.max_tokens,
                temperature=0.0,
            ).strip()
        elapsed = time.perf_counter() - started
        ok = bool(answer.strip()) and case.validator(answer)
        passed += int(ok)
        bucket = category_totals.setdefault(case.category, [0, 0])
        bucket[0] += int(ok)
        bucket[1] += 1
        results.append({
            "name": case.name,
            "category": case.category,
            "prompt": case.prompt,
            "answer": answer,
            "passed": ok,
            "elapsed_seconds": round(elapsed, 3),
        })
        print(f"[{index:02d}/{len(CASES)}] [{'通过' if ok else '失败'}] {case.name} ({elapsed:.2f}s)")
        if not args.brief or not ok:
            print(answer + "\n")

    report = {
        "adapter": str(args.adapter),
        "execution": args.execution,
        "passed": passed,
        "total": len(CASES),
        "score": round(passed / len(CASES), 4),
        "categories": {
            name: {"passed": values[0], "total": values[1]}
            for name, values in sorted(category_totals.items())
        },
        "results": results,
    }
    print(f"训练升级评估：{passed}/{len(CASES)}，得分{report['score']:.1%}")
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    raise SystemExit(0 if passed == len(CASES) else 1)


if __name__ == "__main__":
    main()
