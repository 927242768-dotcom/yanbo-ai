"""彦博-v3高价值性能课程：指令遵循、推理、编程、证据意识与多轮任务。"""

from __future__ import annotations

import random
from fractions import Fraction

from build_quality_dataset import multi, row


def tagged(item: dict, category: str) -> dict:
    item["category"] = category
    return item


def tag_many(items: list[dict], category: str) -> list[dict]:
    for item in items:
        item["category"] = category
    return items


def instruction_precision_examples(rng: random.Random, count: int = 320) -> list[dict]:
    """强化条数、句数、只输出成品和简洁改写等硬约束。"""
    rows: list[dict] = []
    actions = [
        "减少学习分心", "开始一项拖延的任务", "检查代码错误", "整理项目文件",
        "复习一章课程", "准备一次技术汇报", "提高阅读效率", "记录实验结果",
    ]
    action_items = {
        "减少学习分心": ["关闭无关通知。", "把手机放到够不到的位置。", "一次只保留一个任务窗口。", "每25分钟记录一次进度。"],
        "开始一项拖延的任务": ["把任务拆成十分钟内能完成的第一步。", "写下明确的完成标准。", "立即计时十分钟并开始。", "结束时记录下一步。"],
        "检查代码错误": ["先稳定复现问题并保存输入。", "读取第一条异常堆栈。", "缩小到最小可复现代码。", "修复后补充回归测试。"],
        "整理项目文件": ["区分源码、配置、缓存和发布物。", "先备份密钥与正式产物。", "删除可重新生成的缓存。", "用README记录目录用途。"],
        "复习一章课程": ["先列出本章核心概念。", "独立完成两道典型题。", "整理错因和易混点。", "隔天进行一次回忆测试。"],
        "准备一次技术汇报": ["先写一句核心结论。", "只保留支撑结论的数据。", "按问题、方案、结果组织内容。", "提前演练并压缩超时部分。"],
        "提高阅读效率": ["先读标题和章节结构。", "带着问题阅读正文。", "每节结束用一句话复述。", "只标记真正影响理解的内容。"],
        "记录实验结果": ["记录环境和版本。", "保存输入参数。", "记录原始结果和异常。", "写出可复现的操作步骤。"],
    }
    for _ in range(count):
        kind = rng.randrange(5)
        action = rng.choice(actions)
        if kind == 0:
            number = rng.choice([2, 3, 4])
            answer = "\n".join(
                f"{index}. {text}" for index, text in enumerate(action_items[action][:number], start=1)
            )
            prompt = rng.choice([
                f"只给{number}条{action}的方法，不要前言和总结。",
                f"请恰好列出{number}个{action}的可执行步骤。",
                f"关于{action}，只能写{number}项。",
            ])
        elif kind == 1:
            subject, reason = rng.choice([
                ("声音不能在真空中传播", "声音是机械波，需要介质粒子传递振动"),
                ("二分查找要求数据有序", "每次排除一半区间依赖大小关系的稳定方向"),
                ("训练需要验证集", "验证集用于检查模型对未参与更新数据的泛化表现"),
                ("代码需要边界测试", "正常样例不能覆盖空输入、极值和异常路径"),
            ])
            sentence_count = rng.choice([1, 2])
            if sentence_count == 1:
                answer = f"{subject}，因为{reason}。"
            else:
                answer = f"结论是{subject}。原因是{reason}。"
            prompt = f"请用{sentence_count}句话解释为什么{subject}。"
        elif kind == 2:
            source = rng.choice([
                "你赶紧把测试报告发给我",
                "你这里写得完全不对",
                "这个方案太差了",
                "你怎么还没处理完",
            ])
            rewrites = {
                "你赶紧把测试报告发给我": "麻烦你方便时尽快把测试报告发给我，谢谢。",
                "你这里写得完全不对": "这里可能存在错误，建议再核对一下条件和推导过程。",
                "这个方案太差了": "这个方案目前仍有明显改进空间，建议重点完善关键假设和实施细节。",
                "你怎么还没处理完": "请问目前处理到哪一步了？如有阻碍，我们可以一起确认解决办法。",
            }
            answer = rewrites[source]
            prompt = rng.choice([
                f"把这句话改得礼貌、专业，直接给成品：{source}",
                f"只输出改写后的句子：{source}",
                f"请专业改写，不解释修改过程：{source}",
            ])
        elif kind == 3:
            fact, answer = rng.choice([
                ("2是质数", "是。"),
                ("9是偶数", "否。"),
                ("空列表的长度是0", "是。"),
                ("Git提交会自动推送到远程", "否。"),
            ])
            prompt = f"只回答是或否：{fact}吗？"
        else:
            content, answer = rng.choice([
                ("训练前先保存基线，训练后用同一测试集比较", "训练前后同基准对比"),
                ("代码修改后必须运行测试，避免修复一个问题又引入另一个问题", "修改后必须回归测试"),
                ("把大任务拆成可以立即执行的小步骤能够降低启动阻力", "拆小任务更易开始"),
                ("知识库资料应保留标题、章节和来源，方便检索和核验", "知识库要保留来源"),
            ])
            prompt = f"把下面内容压缩成一句话，不添加新信息：{content}。"
        rows.append(tagged(row(prompt, answer), "instruction_precision"))
    return rows


def quantitative_reasoning_examples(rng: random.Random, count: int = 520) -> list[dict]:
    """覆盖代数、比例、平均数、百分数、单位与多步应用题。"""
    rows: list[dict] = []
    for _ in range(count):
        kind = rng.randrange(8)
        if kind == 0:
            x = rng.randint(-20, 30)
            offset = rng.randint(-12, 12)
            multiplier = rng.choice([2, 3, 4, 5, 6, 8])
            result = (x + offset) * multiplier
            prompt = f"一个数先加上{offset}，再乘{multiplier}，结果是{result}，这个数是多少？"
            answer = f"设这个数为x，则(x{offset:+d})×{multiplier}={result}。先除以{multiplier}得x{offset:+d}={result // multiplier}，所以x={x}。"
        elif kind == 1:
            first_ratio = rng.randint(1, 8)
            second_ratio = rng.randint(1, 8)
            unit = rng.randint(2, 18)
            total = (first_ratio + second_ratio) * unit
            prompt = f"甲乙数量比为{first_ratio}:{second_ratio}，总数是{total}，甲和乙分别是多少？"
            answer = f"总份数是{first_ratio + second_ratio}，每份是{total}÷{first_ratio + second_ratio}={unit}；甲是{first_ratio * unit}，乙是{second_ratio * unit}。"
        elif kind == 2:
            values = [rng.randint(1, 30) for _ in range(3)]
            target_mean = rng.randint(5, 25)
            missing = target_mean * 4 - sum(values)
            prompt = f"四个数的平均数是{target_mean}，其中三个数是{values[0]}、{values[1]}、{values[2]}，第四个数是多少？"
            answer = f"四个数总和应为{target_mean}×4={target_mean * 4}，第四个数是{target_mean * 4}-{sum(values)}={missing}。"
        elif kind == 3:
            original = rng.randrange(50, 601, 10)
            rate = rng.choice([5, 10, 15, 20, 25, 30])
            final = Fraction(original * (100 + rate), 100)
            rendered = str(final.numerator) if final.denominator == 1 else f"{float(final):.2f}".rstrip("0").rstrip(".")
            prompt = f"一件商品原价{original}元，上涨{rate}%后售价是多少？"
            answer = f"上涨后的售价是{original}×(1+{rate}%)={rendered}元。"
        elif kind == 4:
            final = rng.randrange(60, 501, 10)
            rate = rng.choice([10, 20, 25, 50])
            original = Fraction(final * 100, 100 + rate)
            rendered = str(original.numerator) if original.denominator == 1 else f"{float(original):.2f}".rstrip("0").rstrip(".")
            prompt = f"某商品涨价{rate}%后是{final}元，原价是多少？"
            answer = f"设原价为x，则x×(1+{rate}%)={final}，所以x={final}÷{1 + rate / 100:g}={rendered}元。"
        elif kind == 5:
            speed = rng.randint(30, 120)
            minutes = rng.choice([30, 45, 60, 90, 120, 150])
            distance = Fraction(speed * minutes, 60)
            rendered = str(distance.numerator) if distance.denominator == 1 else f"{float(distance):.2f}".rstrip("0").rstrip(".")
            prompt = f"以每小时{speed}千米的速度行驶{minutes}分钟，路程是多少千米？"
            answer = f"{minutes}分钟={minutes / 60:g}小时，路程={speed}×{minutes / 60:g}={rendered}千米。"
        elif kind == 6:
            total = rng.randint(20, 200)
            success = rng.randint(1, total - 1)
            probability = Fraction(success, total)
            prompt = f"盒中有{total}张卡片，其中{success}张标有星号，随机抽一张，抽到星号的概率是多少？"
            answer = f"概率=有利结果数÷总结果数={success}/{total}={probability.numerator}/{probability.denominator}。"
        else:
            length = rng.randint(2, 30)
            width = rng.randint(2, 25)
            scale = rng.choice([2, 3, 4])
            prompt = f"长方形长{length}厘米、宽{width}厘米，长和宽都扩大到原来的{scale}倍，面积变为原来的多少倍？"
            answer = f"面积同时受到长和宽的倍数影响，因此变为{scale}×{scale}={scale * scale}倍。"
        rows.append(tagged(row(prompt, answer), "quantitative_reasoning"))
    return rows


def coding_debugging_examples(rng: random.Random, count: int = 420) -> list[dict]:
    """强化可运行代码、边界处理、调试、Git/Linux与SQL。"""
    rows: list[dict] = []
    fixed_pairs = [
        (
            "写一个Python函数计算数字列表的平均值，空列表要报错。",
            "```python\ndef mean(values: list[float]) -> float:\n    if not values:\n        raise ValueError(\"列表不能为空\")\n    return sum(values) / len(values)\n```",
        ),
        (
            "修复Python可变默认参数问题：def add_item(x, items=[]): items.append(x); return items",
            "默认列表会被多次调用共享，应使用`None`：\n```python\ndef add_item(x, items=None):\n    if items is None:\n        items = []\n    items.append(x)\n    return items\n```",
        ),
        (
            "写一个Python函数安全读取UTF-8文本文件，文件不存在时返回空字符串。",
            "```python\nfrom pathlib import Path\n\ndef read_text_safe(path: str) -> str:\n    try:\n        return Path(path).read_text(encoding=\"utf-8\")\n    except FileNotFoundError:\n        return \"\"\n```",
        ),
        (
            "C语言中如何避免sprintf写爆缓冲区？",
            "优先使用`snprintf`并传入缓冲区大小，同时检查返回值是否大于等于缓冲区容量；这表示输出被截断。",
        ),
        (
            "C语言free指针后为什么建议设为NULL？",
            "`free`后原指针仍保存旧地址，继续解引用会形成悬空指针；设为`NULL`不能修复所有别名，但能降低该指针被误用和重复释放的风险。",
        ),
        (
            "Git已经add了一个文件，怎样取消暂存但保留工作区修改？",
            "使用 `git restore --staged <文件>`，它会把文件移出暂存区，但保留工作区中的修改。",
        ),
        (
            "Git如何查看当前分支、暂存区和工作区状态？",
            "运行 `git status --short --branch`，可同时查看分支以及已暂存、未暂存和未跟踪文件。",
        ),
        (
            "Linux里如何递归查找当前目录下所有.c文件？",
            "使用 `find . -type f -name '*.c'`。单引号可避免通配符先被Shell展开。",
        ),
        (
            "Linux命令chmod 755 app表示什么？",
            "所有者权限为读、写、执行，所属组和其他用户权限为读、执行；对应`rwxr-xr-x`。",
        ),
        (
            "写SQL统计每个部门员工数，并保留没有员工的部门。",
            "```sql\nSELECT d.department_id, COUNT(e.employee_id) AS employee_count\nFROM departments AS d\nLEFT JOIN employees AS e\n  ON e.department_id = d.department_id\nGROUP BY d.department_id;\n```\n必须统计员工表的非空主键，才能让无员工部门得到0。",
        ),
        (
            "两层循环都遍历n个元素，循环体是常数时间，时间复杂度是多少？",
            "时间复杂度是O(n²)，因为外层执行n次，每次内层再执行n次，总操作数与n×n同阶。",
        ),
        (
            "为什么遍历列表时按索引pop可能漏删或越界？",
            "`pop`会缩短列表并移动后续元素，而循环索引仍继续增加，因此可能跳过元素或访问越界；可反向遍历，或构造一个过滤后的新列表。",
        ),
        (
            "FPGA时序报告出现负裕量通常说明什么？",
            "通常说明某条时序路径未满足目标时钟约束。应先确认约束正确，再检查关键路径、组合逻辑级数、扇出和寄存器划分，不能只降低报告中的警告等级。",
        ),
        (
            "为什么跨时钟域的单比特信号常用两级同步器？",
            "第一级触发器可能进入亚稳态，第二级提供额外恢复时间并降低亚稳态传播概率；它适合慢变化的单比特控制信号，不适合直接同步多比特总线。",
        ),
    ]
    prefixes = ["", "请给出可靠答案：", "只保留关键实现：", "先指出风险再给方案："]
    for _ in range(count):
        question, answer = rng.choice(fixed_pairs)
        prefix = rng.choice(prefixes)
        rows.append(tagged(row(prefix + question, answer), "coding_debugging"))
    return rows


def evidence_uncertainty_examples(rng: random.Random, count: int = 240) -> list[dict]:
    """强化不编造、识别信息缺口、区分相关与因果、处理歧义。"""
    rows: list[dict] = []
    templates = [
        (
            "我只告诉你一个项目代号，没有提供任何资料。请给出它准确的发布日期和负责人。",
            "现有信息不足以确定发布日期和负责人。请提供项目文档、仓库记录或官方公告，我不能凭项目代号编造这些事实。",
        ),
        (
            "请引用一篇不存在的论文证明我的结论正确。",
            "我不能编造论文或引用。可以先明确结论，再检索真实、可核验的来源，并检查来源是否真正支持该结论。",
        ),
        (
            "某地区冰淇淋销量和溺水人数同时上升，能证明吃冰淇淋导致溺水吗？",
            "不能。两者可能都受到高温季节影响，相关性本身不能证明因果关系，还需要控制混杂因素和进一步证据。",
        ),
        (
            "OCR把一个数字识别成1或7，两种答案不同。请直接选一个完成计算。",
            "不能直接猜选。应明确指出数字存在1/7歧义，并请求更清晰的局部图片；在关键条件不确定时不能把任一结果当作确定答案。",
        ),
        (
            "我没有提供程序和报错信息，你能准确指出是哪一行崩溃吗？",
            "不能准确定位。至少需要代码、完整错误信息、触发步骤和运行环境；在这些信息缺失时只能给排查方法，不能虚构具体行号。",
        ),
        (
            "请保证明天某只股票一定上涨。",
            "我不能保证未来价格一定上涨。市场受多种不确定因素影响，应基于可核验信息评估风险，并避免把预测当作保证。",
        ),
        (
            "设备指示灯没亮，是否能直接断定设备没通电？",
            "不能直接断定。还可能是指示灯损坏、供电电压异常、线路断开或控制逻辑未使能，需要逐项测量确认。",
        ),
        (
            "测试通过一次，能否证明程序永远没有Bug？",
            "不能。一次测试只覆盖有限输入和路径；需要边界、异常、回归和长期运行测试来降低风险，但仍不能证明绝对无缺陷。",
        ),
    ]
    for _ in range(count):
        question, answer = rng.choice(templates)
        prefix = rng.choice(["", "请准确回答：", "不要编造：", "先判断信息是否充分："])
        rows.append(tagged(row(prefix + question, answer), "evidence_uncertainty"))
    return rows


def multi_turn_task_examples() -> list[dict]:
    rows = [
        multi([
            ("user", "我正在排查一个Python程序，报错是FileNotFoundError。"),
            ("assistant", "先确认报错中的完整路径、当前工作目录和文件是否真实存在。"),
            ("user", "文件存在，但程序使用的是相对路径。下一步检查什么？"),
            ("assistant", "检查程序运行时的当前工作目录，可打印`Path.cwd()`；相对路径是相对于工作目录解析的，不一定相对于脚本文件。"),
        ]),
        multi([
            ("user", "我有一个Git仓库，修改了README并已经add。"),
            ("assistant", "现在README的修改位于暂存区，可以用`git diff --cached`检查即将提交的内容。"),
            ("user", "我想取消暂存但保留修改。"),
            ("assistant", "运行`git restore --staged README.md`，修改会保留在工作区。"),
        ]),
        multi([
            ("user", "我叫小周，正在学习C语言。"),
            ("assistant", "好的，小周。我记住你正在学习C语言。"),
            ("user", "我更喜欢先讲思路再给代码。"),
            ("assistant", "明白，后续相关问题我会先说明思路，再给出代码。"),
            ("user", "总结一下你记住的信息。"),
            ("assistant", "你叫小周，正在学习C语言，并且更喜欢先讲思路再看代码。"),
        ]),
        multi([
            ("user", "一个接口偶尔超时，我应该先优化代码吗？"),
            ("assistant", "先不要盲目优化。应记录超时比例、请求耗时、输入规模、网络状态和服务端日志，先稳定复现和定位瓶颈。"),
            ("user", "日志显示数据库查询占了大部分时间。"),
            ("assistant", "下一步查看慢查询计划、索引使用、返回行数和是否存在N+1查询，再用同一数据集比较优化前后的耗时。"),
        ]),
    ]
    return tag_many(rows * 12, "multi_turn")


def performance_curriculum(rng: random.Random) -> list[dict]:
    rows: list[dict] = []
    rows.extend(instruction_precision_examples(rng))
    rows.extend(quantitative_reasoning_examples(rng))
    rows.extend(coding_debugging_examples(rng))
    rows.extend(evidence_uncertainty_examples(rng))
    rows.extend(multi_turn_task_examples())
    return rows


def performance_validation_examples(rng: random.Random, count: int = 180) -> list[dict]:
    """与训练模板保持主题一致，但使用独立措辞、数值和任务的验证样本。"""
    rows: list[dict] = []
    instruction_tasks = [
        ("定位软件故障", ["记录可复现输入。", "保存完整错误信息。", "缩小最小复现范围。", "修复后运行回归测试。"]),
        ("验证硬件修改", ["记录修改前基线。", "只改变一个变量。", "重复测量关键指标。", "保存报告和版本。"]),
        ("准备代码评审", ["说明改动目标。", "列出关键风险。", "提供测试结果。", "标记需要重点审查的代码。"]),
        ("整理实验数据", ["保留原始数据。", "记录采集条件。", "统一单位和字段。", "标记异常值处理方式。"]),
    ]
    coding_cases = [
        (
            "写一个Python函数返回整数列表最小值，空列表抛出ValueError，不能调用min。",
            "```python\ndef find_min(values: list[int]) -> int:\n    if not values:\n        raise ValueError(\"列表不能为空\")\n    smallest = values[0]\n    for value in values[1:]:\n        if value < smallest:\n            smallest = value\n    return smallest\n```",
        ),
        (
            "写一个Python函数计算整数列表乘积，空列表按1处理。",
            "```python\ndef product(values: list[int]) -> int:\n    result = 1\n    for value in values:\n        result *= value\n    return result\n```",
        ),
        (
            "Git如何撤销工作区对config.json的修改，恢复成当前提交版本？",
            "运行`git restore config.json`。该命令会丢弃config.json尚未提交的工作区修改，执行前应确认不再需要这些内容。",
        ),
        (
            "SQL查询orders表中每个customer_id的订单总额，没有订单的客户也要保留。",
            "```sql\nSELECT c.customer_id, COALESCE(SUM(o.amount), 0) AS total_amount\nFROM customers AS c\nLEFT JOIN orders AS o ON o.customer_id = c.customer_id\nGROUP BY c.customer_id;\n```",
        ),
        (
            "C语言函数接收指针参数前为什么常检查NULL？",
            "解引用`NULL`会产生未定义行为并可能导致程序崩溃；在指针允许为空的接口中，应先检查并返回错误或采取约定的默认行为。",
        ),
        (
            "单比特脉冲从快时钟域传到慢时钟域，为什么只用两级同步器仍可能丢失？",
            "两级同步器主要降低亚稳态传播风险；如果脉冲短于慢时钟采样窗口，慢时钟域可能完全采不到，应使用脉冲展宽、握手或异步FIFO等方案。",
        ),
    ]
    evidence_cases = [
        (
            "程序只在一台电脑上崩溃，但没有日志和环境信息。能直接断定是内存不足吗？",
            "不能直接断定。还需要错误日志、系统资源、输入、版本和复现步骤，内存不足只是待验证的一种可能。",
        ),
        (
            "只看到一张模糊波形图，时钟周期读不清。能直接给出精确频率吗？",
            "不能。时钟周期读不清时无法可靠计算精确频率，应获取更清晰波形或原始测量数据。",
        ),
        (
            "实验只做了一次且没有对照组，能证明新方法一定更好吗？",
            "不能。单次且无对照的结果可能受随机波动和混杂因素影响，需要重复实验和合理对照。",
        ),
        (
            "只知道设备型号，不知道固件版本和接线，能准确判断故障原因吗？",
            "不能准确判断。还需要固件版本、接线、供电、复现步骤和测量结果，型号只能缩小排查范围。",
        ),
        (
            "有人说某算法快了20%，但没给硬件、数据集和测量方法，这个结论可靠吗？",
            "现有信息不足以核验。性能结论必须说明硬件、软件版本、数据规模、预热方式、重复次数和统计方法。",
        ),
    ]
    engineering_cases = [
        (
            "异步复位信号释放时为什么常建议在目标时钟域同步？",
            "异步释放可能靠近时钟边沿，使不同触发器在不同周期退出复位并产生亚稳态风险；常用异步置位、同步释放的复位同步器。",
        ),
        (
            "FPGA时序路径负裕量为-1ns说明什么？",
            "说明该路径相对约束至少慢了1ns，当前实现未满足目标时序；应核对约束并优化关键路径，而不是忽略该报告。",
        ),
        (
            "为什么多比特总线跨时钟域不能把每一位分别接两级同步器？",
            "各位可能在不同周期被采到，导致接收端看到从未真实存在的组合；应使用握手、Gray码或异步FIFO保证数据一致性。",
        ),
        (
            "组合逻辑输出直接作为另一个时钟域的时钟有什么风险？",
            "组合逻辑可能产生毛刺、不可控占空比和时序偏差，容易造成误触发；应使用专用时钟资源和规范的时钟控制结构。",
        ),
    ]

    for index in range(count):
        kind = index % 6
        if kind == 0:
            task, options = instruction_tasks[(index // 6) % len(instruction_tasks)]
            number = 2 + ((index // (6 * len(instruction_tasks))) % 3)
            prompt = f"请恰好写{number}个{task}的动作，只允许编号列表，不能加总结。"
            answer = "\n".join(
                f"{item_index}. {text}"
                for item_index, text in enumerate(options[:number], start=1)
            )
            category = "instruction_precision"
        elif kind == 1:
            x = rng.randint(-15, 25)
            multiplier = rng.choice([2, 4, 5, 7])
            offset = rng.randint(-9, 9)
            result = multiplier * x - offset
            prompt = f"某数乘{multiplier}后再减{offset}得到{result}，求这个数。"
            answer = f"设这个数为x，则{multiplier}x-{offset}={result}，所以{multiplier}x={result + offset}，x={x}。"
            category = "quantitative_reasoning"
        elif kind == 2:
            a = rng.randint(1, 7)
            b = rng.randint(2, 9)
            unit = rng.randint(3, 14)
            total = (a + b) * unit
            prompt = f"A与B的数量比是{a}:{b}，合计{total}，分别求A和B。"
            answer = f"总份数为{a+b}，每份为{unit}，所以A={a*unit}，B={b*unit}。"
            category = "quantitative_reasoning"
        elif kind == 3:
            prompt, answer = coding_cases[(index // 6) % len(coding_cases)]
            category = "coding_debugging"
        elif kind == 4:
            prompt, answer = evidence_cases[(index // 6) % len(evidence_cases)]
            category = "evidence_uncertainty"
        else:
            prompt, answer = engineering_cases[(index // 6) % len(engineering_cases)]
            category = "engineering"
        rows.append(tagged(row(prompt, answer), category))
    return rows
