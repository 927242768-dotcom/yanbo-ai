"""彦博-v3第5轮独立鲁棒性评测。

本评测在第5轮训练与引擎修改前建立，用于保存正式模型基线。
题目覆盖严格指令、真实性、数量推理、电子电路、嵌入式、编程、工具和逻辑。
不得把本文件中的题目直接复制进训练数据。
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

from assistant_engine import (
    DEFAULT_ADAPTER_PATH,
    DEFAULT_MODEL_PATH,
    SYSTEM_PROMPT,
    AssistantEngine,
    FallbackBackend,
)
from console_utils import configure_utf8_console


Validator = Callable[[str], bool]


def _searchable(text: str) -> str:
    return re.sub(r"\s+", "", text.casefold())


def contains_all(*words: str) -> Validator:
    return lambda text: all(_searchable(word) in _searchable(text) for word in words)


def contains_any(*words: str) -> Validator:
    return lambda text: any(_searchable(word) in _searchable(text) for word in words)


def excludes_all(*words: str) -> Validator:
    return lambda text: all(word.casefold() not in text.casefold() for word in words)


def combine(*validators: Validator) -> Validator:
    return lambda text: all(validator(text) for validator in validators)


def numbered_count(expected: int) -> Validator:
    def validate(text: str) -> bool:
        markers = re.findall(r"(?m)^\s*(\d+)[.、)）]\s*", text)
        return len(markers) == expected and markers == [str(index) for index in range(1, expected + 1)]

    return validate


def sentence_count(expected: int) -> Validator:
    def validate(text: str) -> bool:
        normalized = re.sub(r"```.*?```", "", text, flags=re.S)
        sentences = re.findall(r"[^。！？!?\n]+[。！？!?]", normalized)
        return len(sentences) == expected

    return validate


def one_line(text: str) -> bool:
    return "\n" not in text.strip()


def only_number(expected: float, tolerance: float = 1e-9) -> Validator:
    def validate(text: str) -> bool:
        value = text.strip().rstrip("。")
        if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", value):
            return False
        return math.isclose(float(value), expected, rel_tol=tolerance, abs_tol=tolerance)

    return validate


def contains_number(expected: float, tolerance: float = 1e-6) -> Validator:
    def validate(text: str) -> bool:
        for raw in re.findall(r"[-+]?\d+(?:\.\d+)?", text.replace(",", "")):
            try:
                if math.isclose(float(raw), expected, rel_tol=tolerance, abs_tol=tolerance):
                    return True
            except ValueError:
                continue
        return False

    return validate


def json_object_with_keys(*keys: str) -> Validator:
    def validate(text: str) -> bool:
        value = text.strip()
        if value.startswith("```"):
            return False
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return False
        return isinstance(parsed, dict) and all(key in parsed for key in keys)

    return validate


@dataclass(frozen=True)
class Case:
    name: str
    category: str
    prompt: str
    validator: Validator


CASES = [
    # 严格指令与成品输出：8
    Case(
        "严格五项清单",
        "instruction",
        "只输出恰好五项嵌入式程序代码评审检查点，必须编号，不要标题、前言或总结。",
        numbered_count(5),
    ),
    Case(
        "严格两句话",
        "instruction",
        "正好用两句话说明轮询与中断的区别，不要标题或列表。",
        combine(sentence_count(2), contains_all("轮询", "中断")),
    ),
    Case(
        "只回答数字复杂算式",
        "instruction",
        "只回答数字：48÷6+7×5等于多少？",
        only_number(43),
    ),
    Case(
        "只回答是否",
        "instruction",
        "只回答“是”或“否”：在标准C中，访问已经free的内存是未定义行为吗？",
        lambda text: text.strip().rstrip("。") == "是",
    ),
    Case(
        "单行短成品",
        "instruction",
        "把“赶紧把板子修好”改成礼貌专业的一句话，只输出成品并保持单行。",
        combine(one_line, contains_any("麻烦", "请", "进度", "修复"), excludes_all("改写", "版本")),
    ),
    Case(
        "纯JSON输出",
        "instruction",
        "只输出合法JSON对象，不要Markdown代码块。对象必须包含status和next_step两个键，status的值为ready。",
        combine(json_object_with_keys("status", "next_step"), contains_all("ready")),
    ),
    Case(
        "严格三个短步骤",
        "instruction",
        "给出恰好三个排查串口无输出的步骤，只能输出编号列表，每项不超过30个汉字。",
        combine(numbered_count(3), lambda text: all(len(line) <= 35 for line in text.splitlines() if line.strip())),
    ),
    Case(
        "标题不带前缀",
        "instruction",
        "给“提交前运行全部自动测试”起一个不超过7个汉字的标题，只输出标题。",
        combine(one_line, lambda text: len(text.strip()) <= 7, contains_any("测试", "提交"), excludes_all("标题", "：", ":")),
    ),

    # 真实性和证据边界：6
    Case(
        "未知内部项目事实",
        "grounding",
        "我只给你内部代号Quartz-884，没有文档、仓库或链接。请准确说出负责人、预算和交付日期。",
        combine(contains_any("无法", "不能", "不足", "未提供"), contains_any("文档", "仓库", "来源", "记录")),
    ),
    Case(
        "缺少波形数据",
        "grounding",
        "我没有上传示波器截图或采样数据，请直接读出占空比和频率。",
        combine(contains_any("无法", "不能", "没有", "未上传"), contains_any("截图", "采样", "数据")),
    ),
    Case(
        "不伪造器件手册",
        "grounding",
        "请编造一份真实存在的MCU数据手册页码，证明它支持5V直接输入。",
        combine(contains_any("不能", "不会", "不应"), contains_any("编造", "伪造", "手册", "核验")),
    ),
    Case(
        "模糊电阻不猜",
        "grounding",
        "照片中的色环可能表示4.7kΩ或47kΩ，图很糊。不要问我，直接选一个计算。",
        combine(contains_any("不能", "不应", "无法"), contains_any("歧义", "清晰", "确认", "两种")),
    ),
    Case(
        "未来版本不保证",
        "grounding",
        "没有官方公告，请保证某芯片厂商下周二一定发布新芯片，并给出具体型号。",
        combine(contains_any("无法", "不能", "不确定"), contains_any("官方", "公告", "来源", "核实")),
    ),
    Case(
        "缺少复现不定责",
        "grounding",
        "没有日志、代码、硬件版本和复现步骤，请确定设备死机的唯一原因。",
        combine(contains_any("无法", "不能", "不足"), contains_any("日志", "代码", "硬件", "复现")),
    ),

    # 通用数量推理：14
    Case(
        "先降后涨百分比",
        "quantitative",
        "商品原价640元，先降价15%，再涨价20%，最终价格是多少？比原价高还是低？",
        combine(contains_number(652.8), contains_any("高", "增加", "多")),
    ),
    Case(
        "连续折扣",
        "quantitative",
        "一件商品标价500元，先打八折，再打九折，实付多少元？相当于原价几折？",
        combine(contains_number(360), contains_any("7.2", "七二", "72%")),
    ),
    Case(
        "加权平均三项",
        "quantitative",
        "作业80分占20%，实验92分占30%，考试86分占50%，总评是多少？",
        contains_number(86.6),
    ),
    Case(
        "速度分钟换算",
        "quantitative",
        "小车速度1.5米每秒，运行2分40秒，路程是多少米？",
        contains_number(240),
    ),
    Case(
        "毫秒转秒",
        "quantitative",
        "2500毫秒等于多少秒？",
        contains_number(2.5),
    ),
    Case(
        "频率周期换算",
        "quantitative",
        "频率为2.5kHz的周期是多少微秒？",
        contains_number(400),
    ),
    Case(
        "比例分配三项",
        "quantitative",
        "甲乙丙数量比为2:3:5，总数为180，三者各是多少？",
        combine(contains_number(36), contains_number(54), contains_number(90)),
    ),
    Case(
        "平均数缺两项和",
        "quantitative",
        "8个数平均为24，已知其中6个数之和为139，剩下两个数的和是多少？",
        contains_number(53),
    ),
    Case(
        "方程带括号",
        "quantitative",
        "解方程：3(x-4)+5=26。",
        contains_number(11),
    ),
    Case(
        "简单二元方程",
        "quantitative",
        "已知x+y=17，x-y=5，求x和y。",
        combine(contains_number(11), contains_number(6)),
    ),
    Case(
        "概率补集",
        "quantitative",
        "某事件发生概率为0.37，它不发生的概率是多少？",
        contains_number(0.63),
    ),
    Case(
        "存储单位",
        "quantitative",
        "按1KiB=1024B计算，3.5KiB是多少字节？",
        contains_number(3584),
    ),
    Case(
        "十六进制转换",
        "quantitative",
        "十六进制0x2F等于十进制多少？",
        contains_number(47),
    ),
    Case(
        "除零边界",
        "quantitative",
        "请计算9/(3-3)。",
        combine(contains_any("不能", "未定义", "除数", "错误"), excludes_all("无穷大")),
    ),

    # 电子、电路与嵌入式：12
    Case(
        "欧姆定律电流",
        "electronics",
        "一个1.2kΩ电阻两端电压为3.3V，电流约为多少mA？",
        contains_number(2.75, tolerance=1e-3),
    ),
    Case(
        "串联电阻",
        "electronics",
        "330Ω、680Ω和1kΩ电阻串联，总电阻是多少Ω？",
        contains_number(2010),
    ),
    Case(
        "并联电阻",
        "electronics",
        "两个电阻1kΩ和2kΩ并联，等效电阻约是多少Ω？",
        contains_number(666.667, tolerance=1e-3),
    ),
    Case(
        "分压计算",
        "electronics",
        "5V输入，R1=3kΩ接上端，R2=2kΩ接地，理想分压输出是多少V？",
        contains_number(2),
    ),
    Case(
        "电阻功率",
        "electronics",
        "10V电压加在2kΩ电阻上，电阻消耗功率是多少mW？",
        contains_number(50),
    ),
    Case(
        "ADC码值",
        "electronics",
        "12位ADC，参考电压3.3V，输入1.65V，理想码值约是多少？码值范围0到4095。",
        contains_number(2048, tolerance=1),
    ),
    Case(
        "ADC分辨率",
        "electronics",
        "10位ADC参考电压5V，每个LSB约是多少mV？",
        contains_number(4.8876, tolerance=1e-3),
    ),
    Case(
        "RC时间常数",
        "electronics",
        "R=10kΩ，C=47µF，RC时间常数是多少秒？",
        contains_number(0.47),
    ),
    Case(
        "RC截止频率",
        "electronics",
        "一阶RC低通中R=1kΩ、C=100nF，截止频率约是多少Hz？",
        contains_number(1591.55, tolerance=1e-3),
    ),
    Case(
        "PWM占空比",
        "electronics",
        "PWM高电平持续0.8ms，周期2ms，占空比是多少？",
        contains_number(40),
    ),
    Case(
        "定时器更新频率",
        "electronics",
        "定时器时钟72MHz，预分频系数为72，自动重装值999，更新频率是多少Hz？按分频后1MHz、计数1000次计算。",
        contains_number(1000),
    ),
    Case(
        "采样定理",
        "electronics",
        "要无混叠采样最高频率8kHz的信号，理论采样率至少应满足什么条件？",
        combine(contains_number(16), contains_any("kHz", "千赫", "大于", "至少")),
    ),

    # 编程与系统边界：8
    Case(
        "Python字典默认参数",
        "coding",
        "修复共享默认字典：def remember(k, v, cache={}): cache[k]=v; return cache",
        combine(contains_all("None", "cache"), contains_any("is None", "== None")),
    ),
    Case(
        "Python深浅拷贝",
        "coding",
        "解释为什么b=a.copy()后修改b[0][0]也会影响嵌套列表a，并给出独立复制方法。",
        combine(contains_any("浅拷贝", "内部", "引用"), contains_any("deepcopy", "copy.deepcopy")),
    ),
    Case(
        "Python文件异常关闭",
        "coding",
        "写Python函数读取UTF-8 JSON文件并解析，文件在异常时也必须关闭。",
        combine(contains_all("with", "json", "utf-8"), contains_any("open", "Path")),
    ),
    Case(
        "Python整数除法边界",
        "coding",
        "写函数safe_div(a,b)，b为0时抛ValueError，否则返回a/b。",
        combine(contains_all("def safe_div", "ValueError", "return"), contains_any("b == 0", "not b")),
    ),
    Case(
        "C乘法溢出",
        "coding",
        "C语言为n个元素分配内存前，如何检查n*sizeof(*p)是否溢出？",
        combine(contains_any("SIZE_MAX", "最大值"), contains_any("/ sizeof", "除以"), contains_all("malloc")),
    ),
    Case(
        "C字符串终止",
        "coding",
        "使用strncpy复制到固定数组后，为什么仍要确保末尾有'\\0'？",
        combine(contains_any("不保证", "未终止", "终止符"), contains_any("越界", "读取", "字符串")),
    ),
    Case(
        "并发原子性",
        "coding",
        "两个线程同时执行counter++是否一定安全？说明原因和修复方法。",
        combine(contains_any("不安全", "不一定", "数据竞争"), contains_any("原子", "互斥", "锁")),
    ),
    Case(
        "复杂度对数",
        "coding",
        "循环中每次把n除以2，直到n小于1，时间复杂度是什么？",
        contains_any("O(log n)", "O(logn)", "对数"),
    ),

    # 工具与工程：6
    Case(
        "Git撤销工作区单文件",
        "tools",
        "怎样丢弃尚未暂存的src/main.c修改，恢复到当前提交？",
        contains_all("git restore", "src/main.c"),
    ),
    Case(
        "Git安全回退提交",
        "tools",
        "一个已经推送并被他人使用的错误提交，通常应如何安全撤销而不改写公共历史？",
        contains_all("git revert"),
    ),
    Case(
        "Linux查大文件",
        "tools",
        "Linux中查找当前目录及子目录大于100MB的普通文件。",
        combine(contains_all("find", "-type f", "-size"), contains_any("+100M", "+100m")),
    ),
    Case(
        "SQL事务原子性",
        "tools",
        "转账要同时扣款和加款，为什么应放在一个数据库事务中？",
        combine(contains_any("原子", "一起成功", "一起失败", "回滚"), contains_any("一致", "事务")),
    ),
    Case(
        "I2C上拉",
        "engineering",
        "为什么I2C的SDA和SCL通常需要上拉电阻？",
        combine(contains_any("开漏", "开集", "只能拉低"), contains_any("高电平", "上拉", "线与")),
    ),
    Case(
        "去耦电容布局",
        "engineering",
        "MCU去耦电容为什么要靠近电源引脚放置？",
        combine(contains_any("回路", "寄生", "电感", "阻抗"), contains_any("瞬态", "噪声", "电流")),
    ),

    # 逻辑与写作：6
    Case(
        "肯定后件",
        "logic",
        "如果晶振不起振，MCU就不运行。现在MCU不运行，能必然推出晶振不起振吗？",
        combine(contains_any("不能", "不一定"), contains_any("电源", "复位", "程序", "其他")),
    ),
    Case(
        "相关不等因果",
        "logic",
        "环境温度升高时风扇转速和故障数都上升，能证明风扇转速导致故障吗？",
        combine(contains_any("不能", "不可以"), contains_any("温度", "共同", "混杂", "相关")),
    ),
    Case(
        "反例推翻全称",
        "logic",
        "有人说所有质数都是奇数。给出反例并判断。",
        combine(contains_number(2), contains_any("错误", "不成立", "反例")),
    ),
    Case(
        "有限测试边界",
        "logic",
        "固件通过了十万次随机测试，能证明所有输入下永远正确吗？",
        combine(contains_any("不能", "不可以"), contains_any("有限", "覆盖", "边界", "路径")),
    ),
    Case(
        "专业催进度",
        "writing",
        "把“你怎么还没把原理图发过来”改成礼貌专业的一句话，只输出成品。",
        combine(one_line, contains_any("原理图", "进度", "发送", "预计"), excludes_all("改写", "版本")),
    ),
    Case(
        "专业指出风险",
        "writing",
        "把“这个电源设计太烂了”改成专业且可执行的一句话，只输出成品。",
        combine(one_line, contains_any("电源", "风险", "评估", "优化", "改进"), excludes_all("改写", "版本")),
    ),
]


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="彦博-v3第5轮独立鲁棒性评测")
    parser.add_argument("--adapter", type=Path, default=DEFAULT_ADAPTER_PATH)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--execution", choices=["raw", "engine"], default="engine")
    parser.add_argument("--engine-backend", choices=["fallback", "native", "auto"], default="native")
    parser.add_argument("--max-tokens", type=int, default=240)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--brief", action="store_true")
    args = parser.parse_args()

    if not args.adapter.exists():
        raise FileNotFoundError(f"适配器不存在：{args.adapter}")
    if args.start < 0 or args.limit < 0:
        raise ValueError("--start和--limit不能小于0")

    selected = CASES[args.start:]
    if args.limit:
        selected = selected[:args.limit]
    if not selected:
        raise ValueError("没有可执行的评测题目")

    engine: AssistantEngine | None = None
    backend: FallbackBackend | None = None
    if args.execution == "engine":
        engine = AssistantEngine(
            backend=args.engine_backend,
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

    results: list[dict] = []
    passed = 0
    category_totals: dict[str, list[int]] = {}
    for local_index, case in enumerate(selected, start=1):
        global_index = args.start + local_index
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
        results.append(
            {
                "index": global_index - 1,
                "name": case.name,
                "category": case.category,
                "prompt": case.prompt,
                "answer": answer,
                "passed": ok,
                "elapsed_seconds": round(elapsed, 3),
            }
        )
        print(f"[{global_index:02d}/{len(CASES)}] [{'通过' if ok else '失败'}] {case.name} ({elapsed:.2f}s)")
        if not args.brief or not ok:
            print(answer + "\n")

    report = {
        "adapter": str(args.adapter),
        "execution": args.execution,
        "engine_backend": args.engine_backend if args.execution == "engine" else "",
        "start": args.start,
        "count": len(selected),
        "suite_total": len(CASES),
        "passed": passed,
        "total": len(selected),
        "score": round(passed / len(selected), 4),
        "categories": {
            name: {"passed": values[0], "total": values[1]}
            for name, values in sorted(category_totals.items())
        },
        "results": results,
    }
    print(f"第5轮鲁棒性评测：{passed}/{len(selected)}，得分{report['score']:.1%}")
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    raise SystemExit(0 if passed == len(selected) else 1)


if __name__ == "__main__":
    main()
