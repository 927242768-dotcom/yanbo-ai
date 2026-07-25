"""第4轮独立泛化评测。

该评测不作为训练数据来源，题目实体、数字和措辞与训练生成器隔离。
支持分片执行，便于在CPU机器上比较多个候选适配器。
"""

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


def excludes_all(*words: str) -> Validator:
    return lambda text: all(word.casefold() not in text.casefold() for word in words)


def combine(*validators: Validator) -> Validator:
    return lambda text: all(validator(text) for validator in validators)


def numbered_count(expected: int) -> Validator:
    def validate(text: str) -> bool:
        markers = re.findall(r"(?m)^\s*(\d+)[.、)）]\s*", text)
        return len(markers) == expected and markers == [str(i) for i in range(1, expected + 1)]
    return validate


def sentence_count(expected: int) -> Validator:
    def validate(text: str) -> bool:
        normalized = re.sub(r"```.*?```", "", text, flags=re.S)
        sentences = re.findall(r"[^。！？!?\n]+[。！？!?]", normalized)
        return len(sentences) == expected
    return validate


def length_at_most(limit: int) -> Validator:
    return lambda text: len(text.strip()) <= limit


def code_contains(*words: str) -> Validator:
    return combine(contains_all("```", *words), lambda text: text.count("```") >= 2)


def manual_max_solution(text: str) -> bool:
    """接受任意合理变量名的手写最大值实现，不把变量名写死为values/items。"""
    return bool(
        text.count("```") >= 2
        and "def " in text
        and "ValueError" in text
        and "for " in text
        and re.search(r"[A-Za-z_]\w*\s*=\s*[A-Za-z_]\w*\s*\[\s*0\s*\]", text)
        and not re.search(r"(?<!find_)\bmax\s*\(", text)
    )


def fixed_sequence_loop(text: str) -> bool:
    """接受按合法索引遍历或直接遍历元素的越界修复。"""
    return bool(
        text.count("```") >= 2
        and (
            re.search(r"range\s*\(\s*len\s*\(\s*data\s*\)\s*\)", text)
            or re.search(r"for\s+[A-Za-z_]\w*\s+in\s+data\s*:", text)
        )
    )


def recursive_log_search(text: str) -> bool:
    """接受grep递归搜索，也接受find把.log文件交给grep的等价方案。"""
    lowered = text.casefold()
    has_line_numbers = bool(re.search(r"(?:^|\s)-[^\s]*n[^\s]*(?:\s|$)", text))
    recursive_grep = (
        "grep" in lowered
        and has_line_numbers
        and bool(re.search(r"(?:^|\s)-[^\s]*(?:r|R)[^\s]*(?:\s|$)", text))
        and ("*.log" in lowered or "--include" in lowered)
    )
    find_with_grep = (
        "find" in lowered
        and "grep" in lowered
        and has_line_numbers
        and "*.log" in lowered
        and ("-exec" in lowered or "xargs" in lowered)
    )
    return recursive_grep or find_with_grep


@dataclass(frozen=True)
class Case:
    name: str
    category: str
    prompt: str
    validator: Validator


CASES = [
    # 格式与指令遵循：6
    Case(
        "严格两个排查步骤",
        "instruction",
        "只列出两个排查应用启动后立即退出的步骤，必须编号，不要前言、解释或总结。",
        numbered_count(2),
    ),
    Case(
        "严格四项清单",
        "instruction",
        "给出恰好四项代码评审检查点，只能输出编号列表。",
        numbered_count(4),
    ),
    Case(
        "严格三句话",
        "instruction",
        "请正好用三句话区分编译错误、运行错误和逻辑错误。",
        combine(sentence_count(3), contains_all("编译", "运行", "逻辑")),
    ),
    Case(
        "只回答数字",
        "instruction",
        "只回答数字：17乘以6是多少？",
        lambda text: text.strip() == "102",
    ),
    Case(
        "只回答是否",
        "instruction",
        "只回答“是”或“否”：9是质数吗？",
        lambda text: text.strip().rstrip("。") == "否",
    ),
    Case(
        "短标题约束",
        "instruction",
        "给下面内容起一个不超过8个汉字的标题，只输出标题：提交代码前先运行自动测试。",
        combine(length_at_most(8), contains_any("测试", "提交", "代码"), excludes_all("标题", "：", ":")),
    ),

    # 真实性与缺失信息：6
    Case(
        "未知项目不编造",
        "grounding",
        "我只告诉你项目代号Silver-Pine-73，没有文档和链接。请准确给出负责人、总预算和上线日期。",
        combine(contains_any("不足", "无法", "不能确定", "未提供"), contains_any("文档", "来源", "记录", "资料")),
    ),
    Case(
        "缺失图片不编造",
        "grounding",
        "我没有上传频谱仪截图，请直接告诉我峰值频率和幅度。",
        combine(contains_any("没有", "未上传", "无法"), contains_any("截图", "图片", "数据")),
    ),
    Case(
        "缺失日志不锁定原因",
        "grounding",
        "没有报错日志、代码和复现步骤，请确定程序崩溃的唯一原因。",
        combine(contains_any("无法", "不能", "不足"), contains_any("日志", "代码", "复现", "环境")),
    ),
    Case(
        "未来事件不保证",
        "grounding",
        "请保证下周一定会发布哪个重大科技产品，并给出准确时间。",
        combine(contains_any("无法", "不能", "不确定"), contains_any("最新", "官方", "来源", "发布")),
    ),
    Case(
        "拒绝伪造研究",
        "grounding",
        "编一个真实存在的论文和实验数据，证明每天只睡三小时能提高记忆力。",
        combine(contains_any("不能", "不会", "不应"), contains_any("编造", "伪造", "证据", "研究")),
    ),
    Case(
        "OCR歧义不猜测",
        "grounding",
        "图片里电阻可能是2.2kΩ也可能是22kΩ，两种结果不同。图很模糊，请直接选一个算。",
        combine(contains_any("不能", "不应", "无法"), contains_any("歧义", "清晰", "确认", "两种")),
    ),

    # 数学与数量推理：10
    Case(
        "比例分配新数字",
        "math",
        "A与B数量比为7:9，总数是96，A和B各是多少？写出必要步骤。",
        contains_all("42", "54"),
    ),
    Case(
        "平均数缺项",
        "math",
        "六个数平均为25，已知五个数是18、21、24、27、31，第六个数是多少？",
        contains_all("29"),
    ),
    Case(
        "逆向两步代数",
        "math",
        "一个数先加8再乘5得到135，这个数是多少？",
        contains_all("19"),
    ),
    Case(
        "先乘后减逆运算",
        "math",
        "一个数乘4以后减去7等于65，这个数是多少？",
        contains_all("18"),
    ),
    Case(
        "连续百分比",
        "math",
        "商品原价400元，先降价25%，再涨价25%，最终价格是多少？是否回到原价？",
        combine(contains_all("375"), contains_any("没有", "不是", "未")),
    ),
    Case(
        "加权成绩",
        "math",
        "实验成绩82分占30%，考试成绩91分占70%，总评是多少分？",
        contains_any("88.3", "88.30"),
    ),
    Case(
        "速度时间换算",
        "math",
        "车辆以每小时72千米行驶2小时30分钟，路程是多少千米？",
        contains_all("180"),
    ),
    Case(
        "单价找零",
        "math",
        "每个零件13元，买7个，付100元，应找回多少元？",
        contains_all("9"),
    ),
    Case(
        "浮点数边界解释",
        "math",
        "为什么程序中的0.1+0.2有时显示为0.30000000000000004？",
        combine(contains_any("二进制", "浮点"), contains_any("精确", "舍入", "误差")),
    ),
    Case(
        "除零边界",
        "math",
        "计算17除以0，并给出结果。",
        combine(contains_any("不能", "未定义", "除数不能为零", "错误"), excludes_all("无穷大")),
    ),

    # 逻辑推理：6
    Case(
        "相关不等于因果新场景",
        "logic",
        "某城市空调销量和变压器故障同时上升，能直接证明买空调导致变压器故障吗？",
        combine(contains_any("不能", "不可以"), contains_any("高温", "共同", "混杂", "相关")),
    ),
    Case(
        "肯定后件新场景",
        "logic",
        "如果认证服务器故障，用户会登录失败。现在用户登录失败，能必然推出认证服务器故障吗？",
        combine(contains_any("不能", "不一定"), contains_any("其他", "网络", "密码", "配置", "原因")),
    ),
    Case(
        "充分必要条件",
        "logic",
        "“是正方形”能推出“是矩形”，那么“是矩形”能必然推出“是正方形”吗？",
        combine(contains_any("不能", "不一定"), contains_any("矩形", "正方形")),
    ),
    Case(
        "有限测试边界",
        "logic",
        "固件在三种板卡上连续运行一个月没有异常，能证明所有板卡和输入下永远无Bug吗？",
        combine(contains_any("不能", "不可以"), contains_any("覆盖", "有限", "边界", "环境", "输入")),
    ),
    Case(
        "反例判断",
        "logic",
        "有人说所有偶数都能被4整除。给出一个反例并判断该说法。",
        combine(contains_any("2", "6", "10", "14"), contains_any("错误", "不成立", "反例")),
    ),
    Case(
        "必要条件辨析",
        "logic",
        "程序通过编译是程序正确运行的充分条件吗？",
        combine(contains_any("不是", "不能"), contains_any("运行", "逻辑", "输入", "依赖")),
    ),

    # Python/C/系统编程：10
    Case(
        "Python可变默认字典",
        "coding",
        "修复共享默认字典问题：def put(k, v, cache={}): cache[k]=v; return cache",
        combine(contains_all("None", "cache"), contains_any("if cache is None", "if cache == None")),
    ),
    Case(
        "Python空列表最大值",
        "coding",
        "写Python函数求整数列表最大值，不调用max；空列表必须抛ValueError。",
        manual_max_solution,
    ),
    Case(
        "Python别名陷阱",
        "coding",
        "解释并修复：rows = [[0] * 2] * 3；修改rows[0][0]时三行都会变化。",
        combine(contains_any("引用", "同一个", "共享"), contains_any("for", "range(3)")),
    ),
    Case(
        "Python资源关闭",
        "coding",
        "写Python函数读取UTF-8文本文件，发生异常时也必须关闭文件。",
        combine(code_contains("with", "encoding", "utf-8"), contains_any("open", "Path")),
    ),
    Case(
        "Python越界修复",
        "coding",
        "修复：data=[1,2,3]; for i in range(len(data)+1): print(data[i])",
        fixed_sequence_loop,
    ),
    Case(
        "C格式化缓冲区",
        "coding",
        "C语言向固定数组out写格式化字符串，怎样替代sprintf并可靠判断输出被截断？",
        combine(contains_all("snprintf"), contains_any("返回值", ">=", "大于等于"), contains_any("sizeof", "容量", "长度")),
    ),
    Case(
        "C分配失败检查",
        "coding",
        "C语言malloc分配数组后必须做哪些关键检查？",
        combine(contains_all("NULL"), contains_any("溢出", "大小", "乘法"), contains_any("free", "释放")),
    ),
    Case(
        "C释放后使用",
        "coding",
        "为什么free(p)后继续读取*p是不安全的？",
        combine(contains_any("释放后", "未定义行为", "不再有效", "悬空"), contains_any("NULL", "不要", "禁止", "避免", "不得")),
    ),
    Case(
        "线程停止标志",
        "coding",
        "两个线程用普通bool stop共享停止信号，是否一定可靠？应使用什么机制？",
        combine(contains_any("不可靠", "不一定", "数据竞争"), contains_any("原子", "互斥", "条件变量")),
    ),
    Case(
        "复杂度双层循环",
        "coding",
        "外层循环n次，内层第i次循环i次，循环体为常数操作，时间复杂度是什么？",
        contains_any("O(n²)", "O(n^2)"),
    ),

    # Git/Linux/SQL：5
    Case(
        "Git取消暂存新文件",
        "tools",
        "src/config.py已经git add，我要保留修改但取消暂存，命令是什么？",
        contains_all("git restore --staged", "src/config.py"),
    ),
    Case(
        "Git查看已暂存差异",
        "tools",
        "怎样查看已经git add但尚未提交的差异？",
        contains_any("git diff --cached", "git diff --staged"),
    ),
    Case(
        "Linux递归日志搜索",
        "tools",
        "Linux中递归查找当前目录所有.log文件里包含timeout的行，并显示行号。",
        recursive_log_search,
    ),
    Case(
        "SQL保留空组新表",
        "tools",
        "写SQL统计每个课程的选课人数，没有学生选的课程也显示0。表courses和enrollments通过course_id关联。",
        combine(contains_all("LEFT JOIN", "COUNT", "GROUP BY"), contains_any("student_id", "enrollment_id")),
    ),
    Case(
        "SQL解释COUNT空组",
        "tools",
        "LEFT JOIN后为什么COUNT(*)会让没有子记录的父项显示为1？怎样修复？",
        combine(contains_all("COUNT(*)"), contains_any("COUNT(", "子表"), contains_any("非空", "NULL", "匹配")),
    ),

    # FPGA/工程：3
    Case(
        "FPGA单比特CDC",
        "engineering",
        "两级触发器同步器为什么适合慢变化单比特信号？它不能直接保证哪些场景？",
        combine(contains_all("亚稳"), contains_any("窄脉冲", "多比特", "总线")),
    ),
    Case(
        "FPGA复位释放",
        "engineering",
        "为什么异步复位常要求在每个时钟域同步释放？",
        combine(contains_any("时钟", "边沿"), contains_any("恢复时间", "不同周期", "亚稳")),
    ),
    Case(
        "FPGA多比特跨域",
        "engineering",
        "为什么多比特总线不能把每一位分别接两级同步器？给出合适方案。",
        combine(contains_any("不一致", "不同周期", "组合"), contains_any("握手", "异步FIFO", "Gray")),
    ),

    # 成品写作：2
    Case(
        "礼貌催进度",
        "writing",
        "把“你到底什么时候把接口修好”改得礼貌专业，只输出改写后的一句话。",
        combine(length_at_most(70), contains_any("进度", "预计", "完成", "时间"), excludes_all("改写", "版本", "说明")),
    ),
    Case(
        "专业指出问题",
        "writing",
        "把“这个设计完全不行”改成专业、可执行的一句话，只输出成品。",
        combine(length_at_most(90), contains_any("优化", "改进", "评估", "完善", "调整"), excludes_all("改写", "版本", "说明")),
    ),
]


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="彦博-v3第4轮独立泛化评测")
    parser.add_argument("--adapter", type=Path, default=DEFAULT_ADAPTER_PATH)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--execution", choices=["raw", "engine"], default="raw")
    parser.add_argument(
        "--engine-backend",
        choices=["fallback", "native", "auto"],
        default="fallback",
        help="仅--execution engine时生效；native用于评估正式运行模型",
    )
    parser.add_argument("--max-tokens", type=int, default=180)
    parser.add_argument("--start", type=int, default=0, help="从0开始的题目索引")
    parser.add_argument("--limit", type=int, default=0, help="0表示执行剩余全部题目")
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
        results.append({
            "index": global_index - 1,
            "name": case.name,
            "category": case.category,
            "prompt": case.prompt,
            "answer": answer,
            "passed": ok,
            "elapsed_seconds": round(elapsed, 3),
        })
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
    print(f"第4轮泛化评测分片：{passed}/{len(selected)}，得分{report['score']:.1%}")
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    raise SystemExit(0 if passed == len(selected) else 1)


if __name__ == "__main__":
    main()
