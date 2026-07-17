"""使用彦博当前版本的高性能模式为每轮训练生成少量高质量导师样本。"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from assistant_engine import AssistantEngine, DISPLAY_NAME
from build_quality_dataset import SYSTEM
from console_utils import configure_utf8_console


PROMPTS = [
    "请讲清楚一元二次方程判别式的作用，并给一个简单例子。",
    "解释平均数、中位数和众数的区别，说明各自适用场景。",
    "一道题：某商品先涨价20%，再降价20%，是否回到原价？请计算说明。",
    "解释为什么除数不能为零，要求通俗但准确。",
    "给出判断一个整数是否为质数的可靠思路和Python实现。",
    "写一个Python函数合并两个有序列表，要求时间复杂度O(n+m)。",
    "写一个Python函数寻找字符串中第一个不重复字符的下标，并处理不存在的情况。",
    "解释Python浅拷贝和深拷贝的区别，并给出短代码示例。",
    "分析这段代码的错误：items=[1,2,3]; for i in range(len(items)): items.pop(i)。",
    "写一个带类型标注和异常处理的Python函数，将CSV文本解析为整数二维列表。",
    "用C语言写一个安全读取整数的简短示例，并说明输入失败时如何处理。",
    "解释C语言指针、地址和解引用之间的关系，给一个最小示例。",
    "写一个C++函数判断括号字符串是否合法，使用栈并说明复杂度。",
    "解释C++中引用和指针的主要区别。",
    "写一条SQL查询：找出每个部门工资最高的员工，说明思路。",
    "解释数据库索引为什么能加速查询，以及它可能带来的代价。",
    "解释HTTP状态码200、400、404、500的含义。",
    "说明同步、异步、并发和并行的区别，避免混淆。",
    "用户说‘所有成功的人都早起，所以早起一定成功’，请指出推理问题。",
    "解释相关性不等于因果性，并给一个生活中的例子。",
    "给出三个能真正执行的复习计划建议，每条包含动作和完成标准。",
    "将‘你写得完全不对’改写为专业、尊重且明确的反馈。",
    "写一段简短邮件，礼貌提醒对方提交延期的文件。",
    "把一段复杂解释写成先结论、后原因、最后例子的结构模板。",
    "解释什么是过拟合，以及训练集、验证集分别有什么作用。",
    "解释学习率过大和过小分别会造成什么问题。",
    "说明大语言模型为什么可能生成错误事实，以及如何降低风险。",
    "解释递归必须有基准条件的原因，并给出阶乘示例。",
    "设计五个测试用例验证除法函数，包括正常、边界和异常情况。",
    "解释哈希表平均查询为何接近O(1)，以及最坏情况为何可能退化。",
    "比较数组、链表、栈和队列的典型用途。",
    "解释二分查找为什么要求数据有序。",
    "写一个JavaScript函数对对象数组按年龄升序排序，不修改原数组。",
    "解释JavaScript中Promise的三个状态。",
    "写一个简单的网页表单校验思路，覆盖空值和非法邮箱。",
    "解释操作系统中进程和线程的区别。",
    "说明死锁的四个必要条件，语言简洁。",
    "解释TCP和UDP的核心区别及典型使用场景。",
    "为什么浮点数比较通常不建议直接使用==？给出改进方式。",
    "请用两句话解释梯度下降，不能使用复杂公式。",
]


def make_row(prompt: str, answer: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": answer},
        ]
    }


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description=f"生成{DISPLAY_NAME}导师训练样本")
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260712)
    args = parser.parse_args()
    if args.round <= 0 or args.count < 0:
        raise ValueError("轮次必须大于0，样本数不能为负数")

    rng = random.Random(args.seed + args.round * 7919)
    prompts = PROMPTS.copy()
    rng.shuffle(prompts)
    selected = prompts[: min(args.count, len(prompts))]
    output = Path(f"data/teacher/round_{args.round:03d}.jsonl")
    output.parent.mkdir(parents=True, exist_ok=True)

    if not selected:
        output.write_text("", encoding="utf-8")
        print("本轮未要求生成导师样本。")
        return

    existing_rows: list[dict] = []
    completed_prompts: set[str] = set()
    if output.exists():
        with output.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                item = json.loads(line)
                existing_rows.append(item)
                messages = item.get("messages", [])
                for message in messages:
                    if message.get("role") == "user":
                        completed_prompts.add(str(message.get("content", "")))
                        break

    remaining = [prompt for prompt in selected if prompt not in completed_prompts]
    print(f"正在生成第{args.round}轮导师样本：目标{len(selected)}条，已完成{len(existing_rows)}条，剩余{len(remaining)}条……")
    if not remaining:
        print(f"导师数据已完整保存：{output}")
        return

    engine = AssistantEngine(backend="native")
    with output.open("a", encoding="utf-8") as file:
        for index, prompt in enumerate(remaining, start=len(existing_rows) + 1):
            engine.reset()
            concise_prompt = prompt + "\n要求：答案准确、结构清楚，尽量控制在400字以内；代码除外。"
            answer = engine.reply(concise_prompt, max_new_tokens=420, temperature=0.15)
            if answer.strip():
                item = make_row(prompt, answer.strip())
                file.write(json.dumps(item, ensure_ascii=False) + "\n")
                file.flush()
                existing_rows.append(item)
            print(f"导师样本 {index}/{len(selected)} 完成", flush=True)

    print(f"导师数据已保存：{output}，有效样本{len(existing_rows)}条")


if __name__ == "__main__":
    main()
