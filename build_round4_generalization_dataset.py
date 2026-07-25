"""构建彦博-v3第4轮泛化强化数据集。

设计原则：
1. 不围绕单一评测题背答案，而是用不同实体、数字、代码和措辞生成可迁移能力；
2. 同时覆盖格式遵循、真实性、数学推理、逻辑、编程、工具、工程与多轮记忆；
3. 混入旧能力回放，降低专项训练造成的灾难性遗忘；
4. 训练集与验证集使用不同模板、实体和数值空间。
"""

from __future__ import annotations

import argparse
import copy
import json
import random
from pathlib import Path
from typing import Callable

from build_quality_dataset import (
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


def tagged(item: dict, category: str) -> dict:
    item["category"] = category
    return item


def user_prompt(item: dict) -> str:
    messages = item.get("messages", [])
    for message in reversed(messages if isinstance(messages, list) else []):
        if isinstance(message, dict) and message.get("role") == "user":
            return str(message.get("content", "")).strip()
    return ""


def deduplicate(rows: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for item in rows:
        key = json.dumps(item.get("messages", []), ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def cycle_generate(count: int, factory: Callable[[int], dict]) -> list[dict]:
    return [factory(index) for index in range(count)]


def instruction_constraint_examples(count: int) -> list[dict]:
    topics = [
        ("排查电脑无法联网", ["确认网线或无线连接是否正常。", "检查IP、网关和DNS配置。", "测试路由器与外网连通性。", "查看防火墙或代理设置。"]),
        ("提高代码可维护性", ["拆分职责单一的函数。", "统一命名和接口约定。", "补充自动测试。", "记录关键设计决策。"]),
        ("准备课程考试", ["按考纲列出知识点。", "用题目检验薄弱环节。", "集中订正错题。", "安排限时模拟。"]),
        ("定位程序性能问题", ["先建立可重复的性能基线。", "使用分析工具定位热点。", "一次只修改一个关键因素。", "用相同输入重新测量。"]),
        ("保护项目数据", ["使用版本控制保存源码。", "定期备份不可再生文件。", "限制敏感凭据访问。", "验证备份可以恢复。"]),
    ]
    templates = [
        "只列出{n}项关于{topic}的建议，必须编号，不要前言和总结。当前场景：{context}。",
        "给我恰好{n}个{topic}步骤；除了编号列表不要输出其他内容。对象是{context}。",
        "关于{topic}，输出正好{n}条，每条一句话。需要处理的是{context}。",
        "请写{n}个{topic}要点，不能多也不能少。具体场景为{context}。",
    ]
    contexts = [
        "api-service", "desktop-client", "training-pipeline", "sensor-board",
        "release-package", "database-worker", "course-review", "network-gateway",
        "mobile-app", "fpga-build", "backup-job", "test-runner",
    ]

    def factory(index: int) -> dict:
        topic, items = topics[index % len(topics)]
        n = 2 + (index // len(topics)) % 3
        template = templates[(index // (len(topics) * 3)) % len(templates)]
        context = f"{contexts[index % len(contexts)]}-{index + 1}"
        answer = "\n".join(f"{number}. {text}" for number, text in enumerate(items[:n], start=1))
        return tagged(
            row(template.format(n=n, topic=topic, context=context), answer),
            "round4_instruction_count",
        )

    rows = cycle_generate(count, factory)
    sentence_topics = [
        ("编译、链接和运行", ["编译把源代码转换为目标文件。", "链接把目标文件和库组合成可执行程序。", "运行由操作系统加载程序并执行指令。"]),
        ("需求、实现和验收", ["需求明确目标、边界和约束。", "实现把需求转化为可运行系统。", "验收依据预先约定的标准判断是否达标。"]),
        ("训练、验证和测试数据", ["训练数据用于更新模型参数。", "验证数据用于选择配置并监控泛化。", "测试数据只用于最终独立评价。"]),
        ("备份、归档和缓存", ["备份用于在数据损坏后恢复。", "归档用于长期保存需要追溯的版本。", "缓存用于加速访问，通常可以重新生成。"]),
    ]
    for index in range(max(20, count // 3)):
        topic, sentences = sentence_topics[index % len(sentence_topics)]
        variants = [
            f"请恰好用三句话区分{topic}。",
            f"只写三句完整的话说明{topic}，不要标题。",
            f"解释{topic}，必须正好三句话。",
        ]
        rows.append(tagged(row(variants[(index // len(sentence_topics)) % len(variants)], "".join(sentences)), "round4_instruction_sentence"))
    return rows


def grounding_examples(count: int) -> list[dict]:
    entities = ["Orchid-17", "NorthStar-X", "Atlas-Delta", "Project-Lumen", "Falcon-R2", "River-9"]
    requests = [
        "负责人、准确预算和正式发布日期",
        "开发团队、采购金额和交付时间",
        "实际客户、合同金额和验收结果",
        "维护人员、服务器地址和上线日期",
    ]
    templates = [
        "我只提供了内部代号{entity}，没有文档或链接。请给出它的{request}。",
        "关于{entity}没有任何可核验资料，但请你确定它的{request}。",
        "现有信息只有名称{entity}。能否准确说出其{request}？",
        "不要说不知道，直接猜测{entity}的{request}。",
    ]

    def factory(index: int) -> dict:
        entity = entities[index % len(entities)] + f"-{100 + index}"
        request = requests[(index // len(entities)) % len(requests)]
        prompt = templates[(index // (len(entities) * len(requests))) % len(templates)].format(
            entity=entity, request=request
        )
        answer = (
            "现有信息不足，无法准确确定这些事实。需要项目文档、仓库记录、合同或官方发布信息进行核验；"
            "不能仅凭内部代号编造人员、金额或日期。"
        )
        return tagged(row(prompt, answer), "round4_grounding_missing_source")

    rows = cycle_generate(count, factory)
    missing_inputs = [
        ("你没有上传示波器截图，却让我读出波形频率。", "当前没有可查看的示波器截图，因此无法读出频率；请上传清晰图片或提供测量数据。"),
        ("我没有贴出报错信息，请直接判断程序崩溃的唯一原因。", "缺少报错、复现步骤和运行环境，无法确定唯一原因；请提供日志、输入和最小复现代码。"),
        ("没有给出数据表，请计算这组数据的平均值。", "当前没有具体数据，无法计算平均值；请提供全部数值。"),
        ("我没发电路图，请指出哪根线接错了。", "当前没有电路图，无法判断具体连线；请上传完整且清晰的原图。"),
    ]
    for index in range(max(24, count // 4)):
        prompt, answer = missing_inputs[index % len(missing_inputs)]
        suffixes = ["", " 请给确定答案。", " 不允许提问。", " 直接猜一个。"]
        rows.append(tagged(row(prompt + suffixes[(index // len(missing_inputs)) % len(suffixes)], answer), "round4_grounding_missing_input"))
    return rows


def math_reasoning_examples(count: int, rng: random.Random) -> list[dict]:
    rows: list[dict] = []
    kinds = ["ratio", "average", "equation", "percent", "rate", "weighted"]
    for index in range(count):
        kind = kinds[index % len(kinds)]
        if kind == "ratio":
            a = rng.randint(2, 9)
            b = rng.randint(2, 9)
            unit = rng.randint(2, 12)
            total = (a + b) * unit
            prompt = f"甲乙数量比为{a}:{b}，总数是{total}，甲乙各是多少？写出必要计算。"
            answer = f"总份数为{a}+{b}={a+b}，每份是{total}÷{a+b}={unit}。甲为{a}×{unit}={a*unit}，乙为{b}×{unit}={b*unit}。"
            category = "round4_math_ratio"
        elif kind == "average":
            values = [rng.randint(5, 40) for _ in range(4)]
            missing = rng.randint(5, 40)
            average = (sum(values) + missing) / 5
            if not average.is_integer():
                missing += 5 - int((sum(values) + missing) % 5)
                average = (sum(values) + missing) / 5
            rendered = "、".join(str(value) for value in values)
            prompt = f"五个数平均数为{int(average)}，已知四个数是{rendered}，第五个数是多少？"
            answer = f"五个数总和为{int(average)}×5={int(average*5)}，已知四数和为{sum(values)}，所以第五个数是{int(average*5)}-{sum(values)}={missing}。"
            category = "round4_math_average"
        elif kind == "equation":
            x = rng.randint(3, 35)
            offset = rng.randint(2, 12)
            multiplier = rng.randint(2, 8)
            result = (x + offset) * multiplier
            prompt = f"一个数先加{offset}再乘{multiplier}得到{result}，这个数是多少？"
            answer = f"逆运算先算{result}÷{multiplier}={x+offset}，再算{x+offset}-{offset}={x}，所以这个数是{x}。"
            category = "round4_math_equation"
        elif kind == "percent":
            original = rng.choice([80, 100, 120, 160, 200, 240, 300])
            up = rng.choice([10, 20, 25, 30])
            down = rng.choice([10, 20, 25, 30])
            raised = original * (1 + up / 100)
            final = raised * (1 - down / 100)
            prompt = f"商品原价{original}元，先涨价{up}%，再降价{down}%，最终价格是多少？是否回到原价？"
            relation = "等于" if abs(final-original) < 1e-9 else ("低于" if final < original else "高于")
            answer = f"涨价后为{original}×(1+{up}%)={raised:g}元，再降价后为{raised:g}×(1-{down}%)={final:g}元。最终价格{relation}原价，并不因为百分比相同就必然抵消。"
            category = "round4_math_percent"
        elif kind == "rate":
            speed = rng.randint(30, 110)
            hours = rng.randint(2, 8)
            minutes = rng.choice([0, 30])
            time_value = hours + minutes / 60
            distance = speed * time_value
            prompt = f"车辆以每小时{speed}千米行驶{hours}小时{minutes}分钟，路程是多少千米？"
            answer = f"{hours}小时{minutes}分钟等于{time_value:g}小时，路程=速度×时间={speed}×{time_value:g}={distance:g}千米。"
            category = "round4_math_rate"
        else:
            score1 = rng.randint(60, 95)
            score2 = rng.randint(60, 95)
            weight1 = rng.choice([20, 30, 40])
            weight2 = 100 - weight1
            result = score1 * weight1 / 100 + score2 * weight2 / 100
            prompt = f"平时成绩{score1}分占{weight1}%，期末成绩{score2}分占{weight2}%，总评是多少分？"
            answer = f"总评={score1}×{weight1}%+{score2}×{weight2}%={result:g}分。"
            category = "round4_math_weighted"
        rows.append(tagged(row(prompt, answer), category))
    return rows


def logic_examples(count: int) -> list[dict]:
    correlations = [
        ("冷饮销量", "中暑人数", "高温天气"),
        ("雨衣销量", "道路拥堵", "降雨"),
        ("搜索热度", "商品退货", "促销活动"),
        ("咖啡销量", "加班人数", "工作强度"),
        ("除湿机销量", "霉变投诉", "潮湿天气"),
    ]
    conditionals = [
        ("数据库不可用", "网站登录失败", "网络、认证服务或配置错误"),
        ("电源断开", "设备停止工作", "保护电路、固件或接口故障"),
        ("编译失败", "没有生成新程序", "构建脚本、链接或权限问题"),
        ("DNS故障", "域名访问失败", "网络、服务器或防火墙问题"),
    ]
    locations = ["海滨区", "高新区", "北城区", "工业园", "大学城", "开发区"]
    systems = ["订单服务", "门禁终端", "数据采集器", "移动客户端", "构建服务器", "监控平台"]
    rows: list[dict] = []
    for index in range(count):
        if index % 3 == 0:
            first, second, common = correlations[(index // 3) % len(correlations)]
            location = locations[(index // 5) % len(locations)]
            period = 2020 + (index % 7)
            prompt = f"{period}年{location}观察到{first}和{second}同时上升，能直接证明前者导致后者吗？"
            answer = f"不能。两者可能同时受到{common}等混杂因素影响；相关性本身不足以证明因果，还需要时间顺序、机制和对照证据。"
            category = "round4_logic_causality"
        elif index % 3 == 1:
            cause, result, alternatives = conditionals[(index // 3) % len(conditionals)]
            system = f"{systems[(index // 4) % len(systems)]}-{index + 1}"
            prompt = f"对{system}而言，如果{cause}，那么{result}。现在出现了{result}，能必然推出{cause}吗？"
            answer = f"不能，这是把充分条件误当成必要条件。{result}还可能由{alternatives}等其他原因造成。"
            category = "round4_logic_converse"
        else:
            times = 50 + (index * 137) % 50000
            system = f"{systems[(index // 3) % len(systems)]}-{index + 1}"
            prompt = f"{system}连续通过{times}次测试，是否能证明所有输入和路径永远没有缺陷？"
            answer = "不能。测试只覆盖有限输入、状态和执行路径；边界、异常、并发和环境变化仍可能暴露问题，测试只能降低风险而不能证明绝对无缺陷。"
            category = "round4_logic_testing"
        rows.append(tagged(row(prompt, answer), category))
    return rows


def python_examples(count: int) -> list[dict]:
    functions = ["collect", "append_item", "remember", "push", "store", "add_value"]
    params = ["items", "values", "records", "cache", "result", "data"]
    rows: list[dict] = []
    for index in range(count):
        kind = index % 5
        fn = f"{functions[index % len(functions)]}_{index + 1}"
        param = params[(index // len(functions)) % len(params)]
        if kind == 0:
            prompt = f"修复Python共享默认列表问题：def {fn}(x, {param}=[]): {param}.append(x); return {param}"
            answer = (
                "可变默认参数只在函数定义时创建一次，应使用`None`作为哨兵：\n"
                f"```python\ndef {fn}(x, {param}=None):\n    if {param} is None:\n        {param} = []\n    {param}.append(x)\n    return {param}\n```"
            )
            category = "round4_python_mutable_default"
        elif kind == 1:
            prompt = f"写Python函数`{fn}`求数值列表平均值，空列表必须抛出ValueError。"
            answer = f"```python\ndef {fn}(values: list[float]) -> float:\n    if not values:\n        raise ValueError(\"列表不能为空\")\n    return sum(values) / len(values)\n```"
            category = "round4_python_boundary"
        elif kind == 2:
            size = 2 + (index % 6)
            value = 1 + index % 17
            variable = f"rows_{index + 1}"
            prompt = f"下面代码为什么会让多行一起变化？{variable} = [[0] * 2] * {size}; {variable}[0][0] = {value}；请修复。"
            answer = f"`[[0] * 2] * {size}`复制的是同一个内部列表的引用。应创建{size}个独立列表：\n```python\n{variable} = [[0] * 2 for _ in range({size})]\n{variable}[0][0] = {value}\n```"
            category = "round4_python_aliasing"
        elif kind == 3:
            prompt = f"写一个Python函数`{fn}`读取UTF-8文本文件，并确保文件总能关闭。"
            answer = f"```python\nfrom pathlib import Path\n\ndef {fn}(path: str | Path) -> str:\n    with Path(path).open(\"r\", encoding=\"utf-8\") as file:\n        return file.read()\n```\n`with`会在正常结束或异常时关闭文件。"
            category = "round4_python_resource"
        else:
            values = [10 + index % 9, 20 + index % 11, 30 + index % 13]
            variable = f"items_{index + 1}"
            rendered = ", ".join(str(value) for value in values)
            prompt = f"修复越界循环：{variable}=[{rendered}]; for i in range(len({variable})+1): print({variable}[i])"
            answer = f"循环多执行了一次。可以直接遍历元素：\n```python\n{variable} = [{rendered}]\nfor item in {variable}:\n    print(item)\n```"
            category = "round4_python_off_by_one"
        rows.append(tagged(row(prompt, answer), category))
    return rows


def c_and_system_examples(count: int) -> list[dict]:
    buffers = ["buf", "output", "message", "line", "path", "text"]
    element_types = ["int", "float", "double", "uint32_t", "char", "Record"]
    rows: list[dict] = []
    for index in range(count):
        kind = index % 4
        buffer_name = f"{buffers[index % len(buffers)]}_{index + 1}"
        if kind == 0:
            capacity = [32, 48, 64, 96, 128, 256][index % 6]
            prompt = f"C语言有固定数组`char {buffer_name}[{capacity}]`，怎样避免sprintf越界并检查截断？"
            answer = f"使用`snprintf({buffer_name}, sizeof {buffer_name}, ...)`限制写入长度，并检查返回值；返回值小于0表示失败，大于等于数组容量表示发生截断。若参数是指针，必须单独传入真实容量。"
            category = "round4_c_buffer"
        elif kind == 1:
            element_type = element_types[index % len(element_types)]
            count_name = f"count_{index + 1}"
            pointer = f"data_{index + 1}"
            prompt = f"C语言要用malloc为`{count_name}`个`{element_type}`分配数组，必须检查哪些问题？给出简短示例。"
            answer = f"先检查`{count_name} * sizeof *{pointer}`是否可能溢出，再检查返回指针是否为`NULL`：\n```c\nif ({count_name} > SIZE_MAX / sizeof *{pointer}) {{\n    return ERROR_TOO_LARGE;\n}}\n{element_type} *{pointer} = malloc({count_name} * sizeof *{pointer});\nif ({pointer} == NULL) {{\n    return ERROR_NO_MEMORY;\n}}\n```\n使用结束后还要`free({pointer})`。"
            category = "round4_c_allocation"
        elif kind == 2:
            pointer = f"ptr_{index + 1}"
            prompt = f"为什么`free({pointer})`后继续读取`*{pointer}`是错误的？应该怎样处理指针？"
            answer = f"`free`后该内存不再属于程序，继续访问属于释放后使用，会产生未定义行为。释放后不要再解引用，并可执行`{pointer} = NULL;`降低误用风险。"
            category = "round4_c_lifetime"
        else:
            flag = f"stop_worker_{index + 1}"
            prompt = f"多线程程序中仅靠普通`bool {flag}`通知另一个线程停止是否可靠？"
            answer = "不一定可靠，普通变量可能产生数据竞争和可见性问题。应使用语言提供的原子变量、互斥量或条件变量，并明确线程退出与资源回收顺序。"
            category = "round4_system_concurrency"
        rows.append(tagged(row(prompt, answer), category))
    return rows


def git_linux_sql_examples(count: int) -> list[dict]:
    files = ["README.md", "src/main.py", "config.yaml", "rtl/top.v", "docs/guide.md", "Makefile"]
    schemas = [
        ("departments", "employees", "department_id", "employee_id"),
        ("teams", "members", "team_id", "member_id"),
        ("projects", "tasks", "project_id", "task_id"),
        ("authors", "articles", "author_id", "article_id"),
    ]
    search_terms = ["ERROR", "timeout", "failed", "disconnect", "overflow", "warning"]
    rows: list[dict] = []
    for index in range(count):
        kind = index % 5
        base_file = files[index % len(files)]
        if "." in base_file:
            stem, suffix = base_file.rsplit(".", 1)
            filename = f"{stem}_{index + 1}.{suffix}"
        else:
            filename = f"{base_file}_{index + 1}"
        if kind == 0:
            prompt = f"{filename}已经git add，怎样取消暂存但保留工作区修改？"
            answer = f"运行 `git restore --staged {filename}`。它只把文件移出暂存区，不会删除工作区中的修改。"
            category = "round4_git_unstage"
        elif kind == 1:
            prompt = f"怎样查看{filename}相对当前提交的工作区差异？"
            answer = f"运行 `git diff -- {filename}` 查看尚未暂存的差异；若要查看已暂存差异，使用 `git diff --cached -- {filename}`。"
            category = "round4_git_diff"
        elif kind == 2:
            term = search_terms[index % len(search_terms)]
            extension = ["log", "txt", "out"][index % 3]
            prompt = f"Linux中怎样递归查找当前目录所有.{extension}文件里包含{term}的行，并显示行号？"
            answer = f"可以运行：\n```bash\ngrep -R --include='*.{extension}' -n '{term}' .\n```\n`-R`递归搜索，`--include`限制文件类型，`-n`显示行号。"
            category = "round4_linux_search"
        elif kind == 3:
            parent_base, child_base, key_base, child_id_base = schemas[(index // 5) % len(schemas)]
            suffix = index + 1
            parent = f"{parent_base}_{suffix}"
            child = f"{child_base}_{suffix}"
            key = f"{key_base}_{suffix}"
            child_id = f"{child_id_base}_{suffix}"
            prompt = f"写SQL统计每个{parent}记录关联的{child}数量，没有子记录也显示0；通过{key}关联。"
            answer = f"```sql\nSELECT p.{key}, COUNT(c.{child_id}) AS child_count\nFROM {parent} AS p\nLEFT JOIN {child} AS c ON c.{key} = p.{key}\nGROUP BY p.{key};\n```\n必须统计子表非空列，空组才会得到0。"
            category = "round4_sql_left_join"
        else:
            parent, child, _, child_id = schemas[(index // 5) % len(schemas)]
            prompt = f"{parent} LEFT JOIN {child}后，为什么`COUNT(*)`可能让没有{child}的记录显示为1？怎样修复？"
            answer = f"`LEFT JOIN`会为没有匹配项的父表记录保留一行，`COUNT(*)`会把这行也计入。应改为统计子表中仅匹配时非空的列，例如`COUNT({child}.{child_id})`。"
            category = "round4_sql_count_null"
        rows.append(tagged(row(prompt, answer), category))
    return rows


def engineering_examples(count: int) -> list[dict]:
    rows: list[dict] = []
    prompts_answers = [
        (
            "信号`{signal}`从{source_clock}跨到{target_clock}，为什么慢变化单比特信号常用两级触发器？它不能直接解决什么？",
            "第一级可能进入亚稳态，第二级提供额外恢复时间，从而降低亚稳态传播概率。它不能保证捕获窄脉冲，也不能保证多比特总线各位一致；这些场景应使用脉冲展宽、握手、Gray码或异步FIFO。",
            "round4_fpga_cdc",
        ),
        (
            "{target_clock}时钟域的异步复位`{signal}`为什么常采用异步置位、同步释放？",
            "异步置位可在时钟未运行时立即复位；同步释放让复位撤销对齐目标时钟，降低不同触发器在不同周期退出复位以及恢复时间违例的风险。每个时钟域应分别同步释放。",
            "round4_fpga_reset",
        ),
        (
            "模块`{module}`的时序逻辑always块中为什么通常使用非阻塞赋值？",
            "非阻塞赋值会先计算右值、再在当前时间步末统一更新寄存器，更符合触发器并行更新行为，也能减少由语句顺序造成的仿真竞争。组合逻辑通常使用阻塞赋值。",
            "round4_fpga_nonblocking",
        ),
        (
            "总线`{bus}`从{source_clock}跨到{target_clock}时，为什么不能每一位都接两级同步器？",
            "各位延迟和稳定时间不同，接收端可能采到源域从未出现过的组合。多比特数据应使用握手保持、Gray码计数器或异步FIFO等协议保证一致性。",
            "round4_fpga_bus",
        ),
        (
            "设备`{module}`已经启用看门狗，是否就能证明它永不死机？",
            "不能。看门狗只能在部分失效场景下触发复位，还可能无法覆盖电源、存储、时钟、外设或看门狗喂狗逻辑本身的问题；仍需故障注入、日志和恢复测试。",
            "round4_embedded_testing",
        ),
    ]
    for index in range(count):
        prompt_template, answer, category = prompts_answers[index % len(prompts_answers)]
        source_clock = f"clk_src_{24 + index % 77}m"
        target_clock = f"clk_dst_{31 + (index * 3) % 101}m"
        prompt = prompt_template.format(
            signal=f"ctrl_{index + 1}",
            source_clock=source_clock,
            target_clock=target_clock,
            module=f"module_{index + 1}",
            bus=f"data_bus_{index + 1}[{3 + index % 29}:0]",
        )
        variants = ["", " 请说明边界。", " 只讲可靠结论。", " 给出工程上正确的处理方式。"]
        rows.append(tagged(row(prompt + variants[(index // len(prompts_answers)) % len(variants)], answer), category))
    return rows


def ambiguity_examples(count: int) -> list[dict]:
    values = [
        ("电阻值", "1kΩ", "7kΩ"),
        ("时钟频率", "50MHz", "80MHz"),
        ("供电电压", "3.3V", "5V"),
        ("电容值", "10nF", "70nF"),
        ("运算符", "+", "÷"),
        ("引脚编号", "3", "8"),
    ]
    templates = [
        "图片中的{subject}可能是{a}也可能是{b}，两种结论不同。请直接选一个继续。",
        "OCR无法区分{subject}是{a}还是{b}，可以猜一个完成计算吗？",
        "截图看不清{subject}，候选为{a}/{b}。不要停下来，随便选。",
    ]
    rows: list[dict] = []
    for index in range(count):
        subject, a, b = values[index % len(values)]
        filename = f"board_capture_{index + 1}.png"
        base_prompt = templates[(index // len(values)) % len(templates)].format(subject=subject, a=a, b=b)
        prompt = f"文件{filename}中，{base_prompt}"
        answer = f"不能直接猜测。{subject}存在{a}/{b}歧义，而且会改变结论；应请求更清晰的局部图片、原始文件或测量数据，确认前只能分别讨论两种情况。"
        rows.append(tagged(row(prompt, answer), "round4_vision_ambiguity"))
    return rows


def writing_examples(count: int) -> list[dict]:
    source_target = [
        ("你怎么还没发测试报告", "麻烦你确认一下测试报告的进度，并在方便时尽快发给我，谢谢。"),
        ("这个代码写得太差了", "这段代码在结构、命名和边界处理方面还有较大优化空间，建议逐项重构并补充测试。"),
        ("你必须马上修好", "这个问题目前比较紧急，麻烦你优先处理，并同步预计完成时间。"),
        ("你根本没看需求", "当前实现与部分需求仍有偏差，建议我们一起核对需求条目并确认修改范围。"),
        ("这个方案完全没用", "该方案目前尚未满足关键目标，需要重新评估假设、成本和实施路径。"),
    ]
    rows: list[dict] = []
    contexts = ["测试负责人", "后端同事", "项目经理", "硬件工程师", "文档维护者", "合作团队"]
    for index in range(count):
        source, target = source_target[index % len(source_target)]
        context = contexts[(index // len(source_target)) % len(contexts)]
        prompts = [
            f"发给{context}：把“{source}”改得礼貌专业，只输出改写后的句子。",
            f"请将“{source}”改成适合与{context}工作沟通的一句话，不要解释。",
            f"准备发给{context}，润色这句话并直接给成品：“{source}”",
        ]
        prompt = prompts[(index // (len(source_target) * len(contexts))) % len(prompts)] + f" 当前事项编号T-{index + 1}。"
        rows.append(tagged(row(prompt, target), "round4_writing_professional"))
    return rows


def memory_examples_round4(count: int) -> list[dict]:
    names = ["小周", "安琪", "林远", "阿诚", "若溪", "嘉宁"]
    topics = ["Linux", "Verilog", "C语言", "概率论", "机械制图", "数据库"]
    preferences = ["先讲思路再给答案", "回答尽量简洁", "代码要有边界检查", "用表格比较", "先给结论", "步骤编号"]
    rows: list[dict] = []
    for index in range(count):
        name = names[index % len(names)]
        topic = topics[(index // len(names)) % len(topics)]
        preference = preferences[(index // (len(names) * len(topics))) % len(preferences)]
        item = multi([
            ("user", f"我叫{name}，最近在学习{topic}。"),
            ("assistant", f"好的，{name}。我记住你最近在学习{topic}。"),
            ("user", f"我喜欢{preference}。"),
            ("assistant", f"明白了，后续相关回答我会尽量{preference}。"),
            ("user", "总结一下我刚才明确告诉你的信息。"),
            ("assistant", f"你叫{name}，最近在学习{topic}，并且偏好{preference}。"),
        ])
        rows.append(tagged(item, "round4_memory_multiturn"))
    return rows


def replay_examples(count: int, rng: random.Random) -> list[dict]:
    sources = [
        (identity_examples(), "round4_replay_identity"),
        (fact_examples(), "round4_replay_facts"),
        (instruction_examples(), "round4_replay_instruction"),
        (coding_examples(), "round4_replay_coding"),
        (uncertainty_examples(), "round4_replay_uncertainty"),
        (adversarial_examples(), "round4_replay_adversarial"),
        (daily_chat_examples(), "round4_replay_chat"),
        (memory_examples(), "round4_replay_memory"),
    ]
    pool: list[dict] = []
    for items, category in sources:
        for item in items:
            cloned = copy.deepcopy(item)
            cloned["category"] = category
            pool.append(cloned)
    result = [copy.deepcopy(pool[index % len(pool)]) for index in range(count)]
    rng.shuffle(result)
    return result


def validation_rows() -> list[dict]:
    cases = [
        ("只列出两个检查服务启动失败的步骤，不要前言和总结。", "1. 查看服务日志和退出码，确认首个明确错误。\n2. 检查配置、端口、权限和依赖是否满足启动条件。", "round4_instruction_count"),
        ("请正好用三句话区分源代码、目标文件和可执行文件。", "源代码是程序员编写和维护的文本。目标文件是源代码编译后形成的机器代码片段。可执行文件由目标文件和所需库链接而成，可以由操作系统加载运行。", "round4_instruction_sentence"),
        ("只有代号Cedar-42，没有任何文档，请准确说出负责人、合同金额和交付日。", "现有信息不足以确定这些事实，需要项目文档、合同或官方记录进行核验，不能仅凭代号编造负责人、金额和日期。", "round4_grounding_missing_source"),
        ("我没有上传逻辑分析仪截图，请直接读出脉冲宽度。", "当前没有可查看的截图，无法读出脉冲宽度；请上传清晰图片或提供采样数据。", "round4_grounding_missing_input"),
        ("甲乙比为4:7，总数55，甲乙各是多少？", "总份数为11，每份为5，所以甲为20，乙为35。", "round4_math_ratio"),
        ("六个数平均为18，其中五个数为10、14、17、21、25，第六个是多少？", "六个数总和为108，已知五数和为87，因此第六个数是21。", "round4_math_average"),
        ("一个数先减6再乘4得到52，这个数是多少？", "逆运算先算52÷4=13，再算13+6=19，所以这个数是19。", "round4_math_equation"),
        ("原价250元，先涨20%再降20%，最终多少元？", "涨价后为300元，再降价后为240元，因此没有回到原价。", "round4_math_percent"),
        ("某地电风扇销量和停电次数同时上升，能证明电风扇导致停电吗？", "不能。高温可能同时提高电风扇使用和电网负荷，相关性不能单独证明因果。", "round4_logic_causality"),
        ("如果磁盘损坏，文件会打不开。现在文件打不开，能必然推出磁盘损坏吗？", "不能，文件打不开还可能由权限、路径、格式或软件故障造成，这是肯定后件。", "round4_logic_converse"),
        ("系统通过了五万次测试，能证明以后绝对没有故障吗？", "不能。测试只覆盖有限输入、状态和路径，只能降低风险，不能证明绝对无故障。", "round4_logic_testing"),
        ("修复：def save(v, box=[]): box.append(v); return box", "应使用`None`作为默认值并在函数内创建列表：\n```python\ndef save(v, box=None):\n    if box is None:\n        box = []\n    box.append(v)\n    return box\n```", "round4_python_mutable_default"),
        ("写Python函数计算列表最小值，空列表抛ValueError，不调用min。", "```python\ndef find_min(values):\n    if not values:\n        raise ValueError(\"列表不能为空\")\n    result = values[0]\n    for value in values[1:]:\n        if value < result:\n            result = value\n    return result\n```", "round4_python_boundary"),
        ("C语言向固定数组name写格式化内容，如何限制长度并判断截断？", "使用`snprintf(name, sizeof name, ...)`，并检查返回值；返回值大于等于数组容量表示截断。", "round4_c_buffer"),
        ("notes.txt已经暂存，取消暂存但保留修改。", "运行 `git restore --staged notes.txt`，工作区修改会保留。", "round4_git_unstage"),
        ("SQL统计每个仓库的库存记录数，没有库存的仓库也显示0，表warehouses和stocks通过warehouse_id关联。", "```sql\nSELECT w.warehouse_id, COUNT(s.stock_id) AS stock_count\nFROM warehouses AS w\nLEFT JOIN stocks AS s ON s.warehouse_id = w.warehouse_id\nGROUP BY w.warehouse_id;\n```", "round4_sql_left_join"),
        ("为什么异步FIFO适合传递跨时钟域多比特数据？", "异步FIFO在写时钟域和读时钟域分别访问存储，并通过Gray码指针同步来判断空满，避免逐位同步造成的数据不一致。", "round4_fpga_bus"),
        ("图片中的电压可能是1.8V或3.3V，看不清，请直接选一个。", "不能直接选择。电压存在1.8V/3.3V歧义并会影响结论，应请求更清晰图片或原始资料。", "round4_vision_ambiguity"),
        ("把“你怎么还没修完”改得礼貌专业，只输出一句话。", "麻烦你同步一下当前修复进度，并说明预计完成时间，谢谢。", "round4_writing_professional"),
    ]
    return [tagged(row(prompt, answer), category) for prompt, answer, category in cases]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for item in rows:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="构建彦博-v3第4轮泛化强化数据")
    parser.add_argument("--seed", type=int, default=20260725)
    parser.add_argument("--per-domain", type=int, default=220)
    parser.add_argument("--replay", type=int, default=700)
    parser.add_argument("--train-output", type=Path, default=Path("data/round4_generalization_train.jsonl"))
    parser.add_argument("--val-output", type=Path, default=Path("data/round4_generalization_val.jsonl"))
    args = parser.parse_args()
    if args.per_domain <= 0 or args.replay < 0:
        raise ValueError("--per-domain必须大于0，--replay不能小于0")

    rng = random.Random(args.seed)
    train: list[dict] = []
    train.extend(instruction_constraint_examples(args.per_domain))
    train.extend(grounding_examples(args.per_domain))
    train.extend(math_reasoning_examples(args.per_domain * 2, rng))
    train.extend(logic_examples(args.per_domain))
    train.extend(python_examples(args.per_domain))
    train.extend(c_and_system_examples(args.per_domain))
    train.extend(git_linux_sql_examples(args.per_domain))
    train.extend(engineering_examples(args.per_domain))
    train.extend(ambiguity_examples(max(80, args.per_domain // 2)))
    train.extend(writing_examples(max(100, args.per_domain // 2)))
    train.extend(memory_examples_round4(max(80, args.per_domain // 2)))
    train.extend(replay_examples(args.replay, rng))
    train = deduplicate(train)
    rng.shuffle(train)

    validation = deduplicate(validation_rows())
    train_prompts = {user_prompt(item) for item in train}
    validation = [item for item in validation if user_prompt(item) not in train_prompts]

    write_jsonl(args.train_output, train)
    write_jsonl(args.val_output, validation)
    print(f"第4轮泛化训练集：{len(train)}条")
    print(f"第4轮独立验证集：{len(validation)}条")


if __name__ == "__main__":
    main()
