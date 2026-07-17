"""为彦博当前版本构建多领域、可按轮次变化的长期训练数据。"""

from __future__ import annotations

import argparse
import json
import random
from fractions import Fraction
from pathlib import Path

from build_quality_dataset import (
    DISPLAY_NAME,
    SYSTEM,
    adversarial_examples,
    coding_examples,
    daily_chat_examples,
    fact_examples,
    identity_examples,
    instruction_examples,
    memory_examples,
    multi,
    row,
    uncertainty_examples,
)
from console_utils import configure_utf8_console


def deduplicate(rows: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for item in rows:
        key = json.dumps(item.get("messages", []), ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def advanced_math_examples(rng: random.Random, count: int) -> list[dict]:
    rows: list[dict] = []
    for _ in range(count):
        kind = rng.randrange(8)
        if kind == 0:
            x = rng.randint(-30, 30)
            a = rng.choice([i for i in range(-12, 13) if i not in (0,)])
            b = rng.randint(-40, 40)
            c = a * x + b
            question = f"解一元一次方程：{a}x{b:+d}={c}。"
            answer = f"移项得{a}x={c-b}，两边除以{a}，所以x={x}。"
        elif kind == 1:
            price = rng.randint(20, 800)
            percent = rng.choice([5, 10, 15, 20, 25, 30, 40, 50])
            value = Fraction(price * percent, 100)
            question = f"{price}的{percent}%是多少？"
            rendered = str(value.numerator) if value.denominator == 1 else f"{float(value):.2f}".rstrip("0").rstrip(".")
            answer = f"{price}×{percent}%={rendered}。"
        elif kind == 2:
            original = rng.randrange(50, 501, 10)
            discount = rng.choice([5, 6, 7, 8, 9])
            paid = Fraction(original * discount, 10)
            question = f"一件商品原价{original}元，打{discount}折后多少钱？"
            rendered = str(paid.numerator) if paid.denominator == 1 else f"{float(paid):.1f}"
            answer = f"打{discount}折就是按原价的{discount * 10}%付款：{original}×{discount / 10:g}={rendered}元。"
        elif kind == 3:
            a, b = rng.randint(1, 12), rng.randint(2, 15)
            c, d = rng.randint(1, 12), rng.randint(2, 15)
            result = Fraction(a, b) + Fraction(c, d)
            question = f"计算分数：{a}/{b}+{c}/{d}。"
            answer = f"通分并相加后得到{result.numerator}/{result.denominator}。"
        elif kind == 4:
            length, width = rng.randint(2, 40), rng.randint(2, 30)
            question = f"长方形长{length}厘米、宽{width}厘米，面积和周长分别是多少？"
            answer = f"面积={length}×{width}={length*width}平方厘米；周长=2×({length}+{width})={2*(length+width)}厘米。"
        elif kind == 5:
            values = [rng.randint(0, 30) for _ in range(rng.randint(3, 6))]
            total = sum(values)
            question = f"数据{values}的平均数是多少？"
            mean = Fraction(total, len(values))
            rendered = str(mean.numerator) if mean.denominator == 1 else f"{float(mean):.3f}".rstrip("0").rstrip(".")
            answer = f"总和是{total}，共有{len(values)}个数，所以平均数是{total}÷{len(values)}={rendered}。"
        elif kind == 6:
            ratio_a, ratio_b = rng.randint(1, 8), rng.randint(1, 8)
            unit = rng.randint(2, 20)
            total = (ratio_a + ratio_b) * unit
            question = f"把{total}按{ratio_a}:{ratio_b}分成两部分，两部分各是多少？"
            answer = f"总份数为{ratio_a+ratio_b}，每份是{unit}，所以两部分分别是{ratio_a*unit}和{ratio_b*unit}。"
        else:
            start = rng.randint(-20, 20)
            step = rng.choice([i for i in range(-8, 9) if i != 0])
            sequence = [start + step * i for i in range(5)]
            next_value = sequence[-1] + step
            question = f"找规律并写出下一项：{', '.join(map(str, sequence))}。"
            answer = f"相邻两项都相差{step}，这是等差数列，下一项是{next_value}。"
        rows.append(row(question, answer))
    return rows


def word_problem_examples(rng: random.Random, count: int) -> list[dict]:
    rows: list[dict] = []
    for _ in range(count):
        kind = rng.randrange(5)
        if kind == 0:
            speed = rng.randint(30, 120)
            hours = rng.randint(2, 9)
            rows.append(row(
                f"汽车以每小时{speed}千米行驶{hours}小时，一共行驶多少千米？",
                f"路程=速度×时间，所以{speed}×{hours}={speed*hours}千米。",
            ))
        elif kind == 1:
            price = rng.randint(3, 50)
            amount = rng.randint(2, 15)
            paid = price * amount + rng.randint(1, 80)
            rows.append(row(
                f"每本书{price}元，买{amount}本，付{paid}元，应找回多少元？",
                f"总价={price}×{amount}={price*amount}元，找回{paid}-{price*amount}={paid-price*amount}元。",
            ))
        elif kind == 2:
            total = rng.randint(30, 200)
            used = rng.randint(1, total - 1)
            rows.append(row(
                f"仓库原有{total}箱货物，运走{used}箱，还剩多少箱？",
                f"用减法计算：{total}-{used}={total-used}，所以还剩{total-used}箱。",
            ))
        elif kind == 3:
            people = rng.randint(20, 100)
            each = rng.randint(2, 10)
            groups, remainder = divmod(people, each)
            rows.append(row(
                f"有{people}人，每{each}人一组，能分成几组，还剩几人？",
                f"{people}÷{each}={groups}余{remainder}，所以能分成{groups}组，还剩{remainder}人。",
            ))
        else:
            work = rng.randint(2, 12)
            days = rng.randint(2, 10)
            rows.append(row(
                f"每天完成{work}道题，连续{days}天一共完成多少道？",
                f"{work}×{days}={work*days}，所以一共完成{work*days}道题。",
            ))
    return rows


def logic_examples(rng: random.Random, count: int) -> list[dict]:
    rows: list[dict] = []
    for _ in range(count):
        kind = rng.randrange(4)
        if kind == 0:
            a = rng.randint(1, 20)
            b = rng.randint(a + 1, a + 20)
            c = rng.randint(b + 1, b + 20)
            rows.append(row(
                f"已知甲得分{a}，乙得分{b}，丙得分{c}，请从高到低排序。",
                "从高到低为：丙、乙、甲。",
            ))
        elif kind == 1:
            item = rng.choice(["苹果", "铅笔", "书本", "水杯"])
            rows.append(row(
                f"所有红色的{item}都放在A箱，这个{item}是红色的。它应放在哪里？",
                "根据已知条件，它应放在A箱。",
            ))
        elif kind == 2:
            rows.append(row(
                "已知所有猫都是动物，小白是一只猫。能推出小白是动物吗？",
                "能。因为所有猫都属于动物，而小白是猫，所以小白是动物。",
            ))
        else:
            statements = [
                ("如果下雨，地面会湿。现在地面湿了，能否必然推出下雨了？", "不能。地面湿还可能由洒水等其他原因造成，这是肯定后件的错误推理。"),
                ("如果设备通电，指示灯可能亮。指示灯没亮，能否直接断定设备没通电？", "不能直接断定，还可能是指示灯损坏或线路故障，需要进一步检查。"),
            ]
            question, answer = rng.choice(statements)
            rows.append(row(question, answer))
    return rows


def hard_case_examples(rng: random.Random, count: int = 240) -> list[dict]:
    """针对历史评估中容易出错的任务进行反例和边界强化。"""
    rows: list[dict] = []
    for _ in range(count):
        kind = rng.randrange(4)
        if kind == 0:
            original = rng.randrange(50, 501, 10)
            rate = rng.choice([5, 10, 15, 20, 25, 30, 40])
            raised = original * (1 + rate / 100)
            final = raised * (1 - rate / 100)
            rows.append(row(
                f"一件{original}元的商品先涨价{rate}%，再降价{rate}%，最后多少钱，是否回到原价？",
                f"先涨价后是{original}×(1+{rate}%)={raised:g}元；再降价后是{raised:g}×(1-{rate}%)={final:g}元。最后没有回到原价，比原价低{original-final:g}元。",
            ))
        elif kind == 1:
            wording = rng.choice([
                "写一个Python函数计算非负整数阶乘，负数必须抛出异常。",
                "用Python实现factorial，n小于0时要raise ValueError。",
                "请写可靠的Python阶乘函数，并处理负数和0。",
            ])
            answer = (
                "```python\n"
                "def factorial(n: int) -> int:\n"
                "    if not isinstance(n, int):\n"
                "        raise TypeError(\"n必须是整数\")\n"
                "    if n < 0:\n"
                "        raise ValueError(\"n不能为负数\")\n"
                "    result = 1\n"
                "    for value in range(2, n + 1):\n"
                "        result *= value\n"
                "    return result\n"
                "```"
            )
            rows.append(row(wording, answer))
        elif kind == 2:
            variable = rng.choice(["i", "n", "value", "index"])
            limit = rng.randint(2, 10)
            broken = f"for {variable} in range({limit}) print({variable})"
            rows.append(row(
                f"这段Python代码有什么语法错误：{broken}",
                f"`for`语句头部末尾缺少冒号。正确写法是：\n```python\nfor {variable} in range({limit}):\n    print({variable})\n```",
            ))
        else:
            rows.append(row(
                "两个现象同时出现，就能证明其中一个导致另一个吗？",
                "不能。相关性可能来自共同原因、反向因果或巧合，需要时间顺序、机制和对照证据等才能支持因果结论。",
            ))
    return rows


def programming_curriculum() -> list[dict]:
    pairs = [
        ("写一个Python函数计算阶乘，并检查负数输入。", "```python\ndef factorial(n: int) -> int:\n    if n < 0:\n        raise ValueError(\"n不能为负数\")\n    result = 1\n    for value in range(2, n + 1):\n        result *= value\n    return result\n```"),
        ("写一个Python函数判断字符串是否为回文，忽略大小写。", "```python\ndef is_palindrome(text: str) -> bool:\n    normalized = text.casefold()\n    return normalized == normalized[::-1]\n```"),
        ("Python中如何去重并保持原顺序？", "```python\ndef unique_in_order(items):\n    seen = set()\n    result = []\n    for item in items:\n        if item not in seen:\n            seen.add(item)\n            result.append(item)\n    return result\n```"),
        ("写一个Python二分查找函数。", "```python\ndef binary_search(values: list[int], target: int) -> int:\n    left, right = 0, len(values) - 1\n    while left <= right:\n        middle = (left + right) // 2\n        if values[middle] == target:\n            return middle\n        if values[middle] < target:\n            left = middle + 1\n        else:\n            right = middle - 1\n    return -1\n```\n输入列表必须已按升序排列。"),
        ("写一个Python函数统计单词频率。", "```python\nfrom collections import Counter\n\ndef word_counts(text: str) -> dict[str, int]:\n    words = text.lower().split()\n    return dict(Counter(words))\n```"),
        ("Python读取JSON文件时如何处理文件不存在和格式错误？", "```python\nimport json\nfrom pathlib import Path\n\ndef load_json(path: str):\n    try:\n        return json.loads(Path(path).read_text(encoding=\"utf-8\"))\n    except FileNotFoundError:\n        return None\n    except json.JSONDecodeError as exc:\n        raise ValueError(\"JSON格式无效\") from exc\n```"),
        ("C语言中数组越界有什么风险？", "数组越界会访问不属于该数组的内存，可能导致数据破坏、崩溃或安全漏洞。C语言通常不会自动进行边界检查，因此必须确保下标在0到长度减1之间。"),
        ("写一个C函数交换两个整数。", "```c\nvoid swap_int(int *a, int *b) {\n    int temp = *a;\n    *a = *b;\n    *b = temp;\n}\n```\n调用时传入两个整数的地址，并确保指针有效。"),
        ("C语言中malloc后为什么要free？", "`malloc`分配的堆内存不会自动释放；不再使用时调用`free`可以避免内存泄漏。释放后不要再次访问该指针，并可将其设为`NULL`。"),
        ("C++中vector和普通数组有什么区别？", "`std::vector`可以动态改变长度，自动管理内存并提供`size()`等接口；普通数组长度通常固定，边界和内存管理更依赖程序员。"),
        ("写一个C++示例对vector升序排序。", "```cpp\n#include <algorithm>\n#include <vector>\n\nstd::vector<int> values{4, 1, 3, 2};\nstd::sort(values.begin(), values.end());\n```"),
        ("JavaScript中map和forEach有什么区别？", "`map`会根据回调结果创建并返回一个新数组；`forEach`主要用于遍历和执行副作用，返回值通常不用于生成新数组。"),
        ("写一个JavaScript异步请求示例并检查错误。", "```javascript\nasync function loadData(url) {\n  const response = await fetch(url);\n  if (!response.ok) {\n    throw new Error(`HTTP ${response.status}`);\n  }\n  return await response.json();\n}\n```"),
        ("SQL中INNER JOIN有什么作用？", "`INNER JOIN`按照连接条件返回两张表中能够匹配的行；任一侧没有匹配的行不会出现在结果中。"),
        ("写一条SQL查询，统计每个部门的员工人数。", "```sql\nSELECT department_id, COUNT(*) AS employee_count\nFROM employees\nGROUP BY department_id;\n```"),
        ("这段Python代码为什么有共享默认列表问题：def add(x, items=[]): items.append(x); return items", "默认参数只在函数定义时创建一次，因此多次调用会复用同一个列表。应改为：\n```python\ndef add(x, items=None):\n    if items is None:\n        items = []\n    items.append(x)\n    return items\n```"),
        ("分析复杂度：遍历长度为n的列表并对每个元素做常数时间操作。", "时间复杂度是O(n)，因为每个元素访问一次；除输入和少量临时变量外，额外空间复杂度通常是O(1)。"),
        ("如何给函数写一个基本单元测试？", "先选择正常输入、边界输入和异常输入，分别断言返回值或异常。例如使用`pytest`：\n```python\ndef test_is_even():\n    assert is_even(2) is True\n    assert is_even(3) is False\n    assert is_even(0) is True\n```"),
    ]
    prefixes = ["", "请给出可靠答案：", "先说明关键点："]
    rows: list[dict] = []
    for question, answer in pairs:
        for prefix in prefixes:
            rows.append(row(prefix + question, answer))
    return rows


def writing_and_chat_curriculum() -> list[dict]:
    return [
        row("把‘你这个地方写错了’改成友好但明确的表达。", "这里可能存在一个错误，建议再检查一下这一部分的条件和计算过程。"),
        row("把下面内容压缩成一句话：学习时关闭通知、把手机放远、一次只做一件事，都能减少分心。", "关闭通知、远离手机并专注单一任务有助于减少学习分心。"),
        row("为一份编程学习计划写三个阶段。", "1. 基础阶段：掌握语法、数据类型、流程控制和函数。\n2. 实践阶段：完成小项目并学习调试、测试和版本管理。\n3. 提升阶段：学习数据结构、算法和目标方向的框架。"),
        row("用户说‘我完全学不会’，请自然回应。", "现在觉得困难不代表学不会。先找出最卡住的一个知识点，把它拆成一个小例子，我们可以从那里开始。"),
        row("写一段简短的道歉消息，说明回复晚了。", "抱歉现在才回复，之前有些事情耽搁了。感谢你的耐心等待。"),
        row("解释问题时应该先做什么？", "先确认问题和已知条件，再直接给出核心结论，随后按步骤解释依据，并检查是否满足用户要求的格式。"),
        row("用户只要求标题时应该怎么回答？", "只给出标题，不额外添加解释、前言或多个备选，除非用户明确要求。"),
        row("如何判断一个建议是否可执行？", "可执行的建议应包含明确动作、开始条件、所需时间和可检查的完成标准，而不是只说‘努力’或‘自律’。"),
    ]


def image_ocr_examples() -> list[dict]:
    """训练模型处理图片文字识别结果中的缺字、错字和公式符号。"""
    pairs = [
        (
            "图片文字识别结果：题目：17 + 25 = ？。请解答。",
            "题目是计算17+25。17+25=42，所以答案是42。",
        ),
        (
            "图片文字识别结果：小明有17个苹果，又买了25个苹果，现在一共有多少个苹果？",
            "用加法计算：17+25=42，所以现在一共有42个苹果。",
        ),
        (
            "图片文字识别结果：3x + 5 = 20。求x。",
            "移项得3x=15，两边除以3，所以x=5。",
        ),
        (
            "OCR可能把‘÷’识别成了‘+’：题目原文显示48 ? 6 = 8。应该怎么处理？",
            "因为48÷6=8，而48+6不等于8，所以结合等式结果可判断该符号最可能是除号；应说明这是依据上下文作出的纠正。",
        ),
        (
            "图片文字识别结果只有‘已知三角形ABC，求’，后续条件没有识别出来。请做题。",
            "当前识别结果缺少关键已知条件和所求内容，无法唯一解答。请重新拍摄完整题目，保证画面清晰且不要裁掉题干。",
        ),
        (
            "图片中代码识别为：for i in range(3) print(i)。请检查。",
            "`for`语句末尾缺少冒号，循环体也需要缩进：\n```python\nfor i in range(3):\n    print(i)\n```",
        ),
        (
            "图片文字识别结果：100元商品先涨20%，再降20%，最后是多少？",
            "涨价后为100×1.2=120元，再降价后为120×0.8=96元，因此最后是96元，没有回到原价。",
        ),
        (
            "识别图片文字时发现数字可能是‘1’或‘7’，而两种情况会得到不同答案。应该怎么办？",
            "应明确指出该数字存在‘1/7’歧义，并请用户上传更清晰的局部图片，不能自行选择一个数字后当作确定题目解答。",
        ),
    ]
    rows: list[dict] = []
    for question, answer in pairs:
        rows.extend([row(question, answer), row("请准确处理：" + question, answer)])
    return rows


def heldout_validation(seed: int) -> list[dict]:
    rng = random.Random(seed)
    rows: list[dict] = []
    rows.extend(advanced_math_examples(rng, 80))
    rows.extend(word_problem_examples(rng, 40))
    rows.extend(logic_examples(rng, 35))
    rows.extend([
        row("请用一句话说明递归必须具备什么。", "递归必须有能够停止继续调用的基准条件，否则可能无限递归。"),
        row("元组能通过索引读取元素吗？", "能。元组不可直接修改元素，但支持索引和切片读取。"),
        row("代码回答中最重要的质量要求是什么？", "代码应正确、可运行、处理关键边界，并与解释保持一致。"),
    ])
    return deduplicate(rows)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for item in rows:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")


def load_teacher_rows(round_number: int) -> list[dict]:
    path = Path(f"data/teacher/round_{round_number:03d}.jsonl")
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description=f"构建{DISPLAY_NAME}多领域训练数据")
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20260712)
    args = parser.parse_args()
    if args.round <= 0:
        raise ValueError("--round必须大于0")

    rng = random.Random(args.seed + args.round * 1009)
    train_rows: list[dict] = []
    train_rows.extend(identity_examples())
    train_rows.extend(fact_examples())
    train_rows.extend(instruction_examples())
    train_rows.extend(coding_examples())
    train_rows.extend(uncertainty_examples())
    train_rows.extend(daily_chat_examples())
    train_rows.extend(memory_examples())
    train_rows.extend(adversarial_examples())
    train_rows.extend(advanced_math_examples(rng, 720))
    train_rows.extend(word_problem_examples(rng, 360))
    train_rows.extend(logic_examples(rng, 260))
    train_rows.extend(programming_curriculum())
    train_rows.extend(hard_case_examples(rng, 280))
    train_rows.extend(writing_and_chat_curriculum())
    train_rows.extend(image_ocr_examples() * 4)
    teacher_rows = load_teacher_rows(args.round)
    train_rows.extend(teacher_rows)
    train_rows = deduplicate(train_rows)
    rng.shuffle(train_rows)

    val_rows = heldout_validation(args.seed + args.round * 1009 + 999_983)
    write_jsonl(Path("data/quality_sft_train.jsonl"), train_rows)
    write_jsonl(Path("data/quality_sft_val.jsonl"), val_rows)
    archive = Path(f"data/rounds/round_{args.round:03d}_train.jsonl")
    write_jsonl(archive, train_rows)

    print(f"{DISPLAY_NAME}第{args.round}轮数据完成：训练{len(train_rows)}条，验证{len(val_rows)}条")
    print(f"本轮导师样本：{len(teacher_rows)}条")
    print(f"训练数据归档：{archive}")


if __name__ == "__main__":
    main()
