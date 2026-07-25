"""构建彦博-v3兼容模型的纠错强化数据集。

该课程针对真实生成评测中的持续失败项：事实依据、因果判断、严格句数、
Python可变默认参数、C缓冲区安全、Git取消暂存、SQL左连接、OCR歧义、
FPGA跨时钟域与测试边界。训练集与验证集使用不同实体和措辞，避免泄漏。
"""

from __future__ import annotations

import argparse
import copy
import json
import random
from pathlib import Path

from build_quality_dataset import (
    adversarial_examples,
    coding_examples,
    fact_examples,
    identity_examples,
    instruction_examples,
    row,
    uncertainty_examples,
)
from console_utils import configure_utf8_console


def tagged(item: dict, category: str) -> dict:
    item["category"] = category
    return item


def last_user_prompt(item: dict) -> str:
    for message in reversed(item.get("messages", [])):
        if message.get("role") == "user":
            return str(message.get("content", "")).strip()
    return ""


def deduplicate(rows: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for item in rows:
        key = json.dumps(item.get("messages", []), ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def exact_sentence_examples(count: int) -> list[dict]:
    concepts = [
        (
            "训练集、验证集和测试集",
            [
                "训练集用于更新模型参数。",
                "验证集用于选择配置并监控泛化。",
                "测试集用于最终独立评估，不能参与调参。",
            ],
        ),
        (
            "需求、设计和测试",
            [
                "需求定义系统要解决的问题和验收目标。",
                "设计把需求转化为结构、接口和实现方案。",
                "测试依据需求验证实现，并反馈设计缺陷。",
            ],
        ),
        (
            "源码、缓存和发布包",
            [
                "源码是需要长期维护和版本控制的输入。",
                "缓存可以重新生成，通常不应提交到仓库。",
                "发布包是交付产物，应按版本保存并校验。",
            ],
        ),
        (
            "训练损失、验证损失和任务得分",
            [
                "训练损失反映模型对训练样本的拟合程度。",
                "验证损失用于观察未参与更新数据上的泛化趋势。",
                "任务得分直接衡量目标能力，三者不能互相替代。",
            ],
        ),
        (
            "进程、线程和协程",
            [
                "进程通常拥有独立地址空间。",
                "线程共享进程资源并由操作系统调度。",
                "协程通常在用户态协作切换，适合大量等待任务。",
            ],
        ),
    ]
    templates = [
        "请恰好用三句话说明{concept}的作用。",
        "解释{concept}，只能写三句话，不要前言。",
        "关于{concept}，输出正好三句，每句以句号结束。",
        "只写三句话区分{concept}，不能合并成一句。",
        "用三句完整的话分别说明{concept}。",
    ]
    rows: list[dict] = []
    for index in range(count):
        concept, sentences = concepts[index % len(concepts)]
        template = templates[(index // len(concepts)) % len(templates)]
        prompt = template.format(concept=concept)
        suffix = index // (len(concepts) * len(templates))
        if suffix:
            prompt += f" 这是第{suffix + 1}组独立练习。"
        rows.append(tagged(row(prompt, "".join(sentences)), "remedy_sentence_count"))
    return rows


def grounding_examples(count: int) -> list[dict]:
    templates = [
        "只知道项目代号{entity}，没有任何资料。请准确给出负责人、预算和发布日期。",
        "我没有提供文档，仅告诉你名称{entity}。请确定团队、成本与发布时间。",
        "关于{entity}没有可核验来源，你能直接说出负责人和金额吗？",
        "请根据代号{entity}推断准确负责人、发布日期和预算，不要说不知道。",
        "现有信息只有{entity}这个名称。请给出它的真实负责人和发布计划。",
    ]
    rows: list[dict] = []
    for index in range(count):
        entity = f"Project-{chr(65 + index % 26)}{1000 + index}"
        prompt = templates[index % len(templates)].format(entity=entity)
        answer = (
            "现有信息不足以确定这些事实。需要项目文档、仓库记录或官方来源进行核验；"
            "不能仅凭一个代号编造负责人、预算和发布日期。"
        )
        rows.append(tagged(row(prompt, answer), "remedy_grounding"))
    return rows


def causality_examples(count: int) -> list[dict]:
    pairs = [
        ("雨伞销量", "交通事故", "降雨天气"),
        ("冷饮销量", "中暑人数", "高温"),
        ("雨衣销量", "道路拥堵", "降雨"),
        ("空调使用量", "电网故障", "炎热天气"),
        ("搜索量", "产品退货", "促销活动"),
        ("防晒霜销量", "空调故障", "高温季节"),
        ("咖啡销量", "加班人数", "工作强度"),
        ("药品销量", "门诊人数", "流行疾病"),
    ]
    templates = [
        "某地{first}和{second}同时上升，能直接证明前者导致后者吗？",
        "观察到{first}与{second}正相关，是否足以推出因果关系？",
        "{first}增加时{second}也增加，可以断言第一项造成第二项吗？",
        "仅凭{first}和{second}同步变化，能证明因果吗？",
    ]
    rows: list[dict] = []
    for index in range(count):
        first, second, common = pairs[index % len(pairs)]
        prompt = templates[(index // len(pairs)) % len(templates)].format(
            first=first, second=second
        )
        prompt += f" 样本编号{index + 1}。"
        answer = (
            f"不能。两者可能都受到{common}等共同因素影响；相关性不能单独证明因果关系，"
            "还需要时间顺序、作用机制、对照实验和混杂因素控制。"
        )
        rows.append(tagged(row(prompt, answer), "remedy_causality"))
    return rows


def mutable_default_examples(count: int) -> list[dict]:
    functions = ["collect", "append_value", "stash", "remember", "push_entry", "add_record"]
    parameters = ["items", "values", "data", "records", "cache", "result"]
    templates = [
        "修复共享默认列表问题：def {fn}(x, {param}=[]): {param}.append(x); return {param}",
        "这段Python函数多次调用会共享列表，请解释并修复：def {fn}(x, {param}=[]): {param}.append(x); return {param}",
        "把下面函数改成每次省略参数都创建新列表：def {fn}(x, {param}=[]): {param}.append(x); return {param}",
        "Python可变默认参数有Bug，请给正确代码：def {fn}(x, {param}=[]): {param}.append(x); return {param}",
    ]
    rows: list[dict] = []
    for index in range(count):
        fn = functions[index % len(functions)]
        param = parameters[(index // len(functions)) % len(parameters)]
        prompt = templates[(index // (len(functions) * len(parameters))) % len(templates)].format(
            fn=fn, param=param
        )
        prompt += f" 变体{index + 1}。"
        answer = (
            "默认列表只在函数定义时创建一次，会被后续调用共享。应使用`None`作为哨兵：\n"
            f"```python\ndef {fn}(x, {param}=None):\n"
            f"    if {param} is None:\n"
            f"        {param} = []\n"
            f"    {param}.append(x)\n"
            f"    return {param}\n```"
        )
        rows.append(tagged(row(prompt, answer), "remedy_python_default"))
    return rows


def c_buffer_examples(count: int) -> list[dict]:
    buffers = ["buf", "output", "message", "path", "line", "text"]
    templates = [
        "C语言用sprintf写入{buffer}时，怎样降低缓冲区溢出风险？",
        "请给出比sprintf更安全的格式化写法，并说明怎样检查{buffer}是否被截断。",
        "固定长度字符数组{buffer}需要拼接格式化字符串，如何安全实现？",
        "为什么应使用snprintf代替sprintf？请说明容量参数和返回值检查。",
        "C代码格式化输出到{buffer}，怎样避免越界写入？",
    ]
    rows: list[dict] = []
    for index in range(count):
        buffer_name = buffers[index % len(buffers)]
        prompt = templates[(index // len(buffers)) % len(templates)].format(buffer=buffer_name)
        prompt += f" 场景{index + 1}。"
        answer = (
            f"优先使用`snprintf({buffer_name}, sizeof {buffer_name}, ...)`并传入缓冲区容量。"
            "检查返回值：若返回值小于0表示编码失败，若大于等于缓冲区容量表示输出被截断；"
            "同时确保缓冲区真实是数组，指针场景要单独传入有效容量。"
        )
        rows.append(tagged(row(prompt, answer), "remedy_c_buffer"))
    return rows


def git_unstage_examples(count: int) -> list[dict]:
    files = [
        "README.md", "config.json", "main.py", "notes.md", "src/app.c", "docs/guide.md",
        "Makefile", "settings.yaml", "mobile/index.html", "rtl/top.v",
    ]
    templates = [
        "{file}已经git add，怎样取消暂存但保留工作区内容？",
        "我误把{file}加入暂存区，不想丢修改，应该执行什么命令？",
        "只撤销{file}的暂存状态，文件修改继续保留。给出Git命令。",
        "如何把{file}从暂存区移出，但不恢复工作区文件？",
        "Git中保留{file}修改并取消add，命令是什么？",
    ]
    rows: list[dict] = []
    for index in range(count):
        filename = files[index % len(files)]
        prompt = templates[(index // len(files)) % len(templates)].format(file=filename)
        prompt += f" 练习{index + 1}。"
        answer = (
            f"运行 `git restore --staged {filename}`。"
            "它只把文件移出暂存区，不会删除工作区中的修改。"
        )
        rows.append(tagged(row(prompt, answer), "remedy_git_unstage"))
    return rows


def sql_left_join_examples(count: int) -> list[dict]:
    schemas = [
        ("departments", "employees", "department_id", "employee_id", "employee_count"),
        ("teams", "members", "team_id", "member_id", "member_count"),
        ("projects", "tasks", "project_id", "task_id", "task_count"),
        ("categories", "products", "category_id", "product_id", "product_count"),
        ("classes", "students", "class_id", "student_id", "student_count"),
        ("warehouses", "stocks", "warehouse_id", "stock_id", "stock_count"),
    ]
    templates = [
        "写SQL统计每个{parent}记录对应的{child}数量，没有{child}的也必须显示0。",
        "表{parent}与{child}通过{key}关联，查询每个{key}的{child}数量并保留空组。",
        "怎样用SQL保留{parent}全部记录，同时统计关联{child}行数？",
        "查询每个{parent}的{child}数量，即使没有子记录也显示0。",
    ]
    rows: list[dict] = []
    for index in range(count):
        parent, child, key, child_id, alias = schemas[index % len(schemas)]
        prompt = templates[(index // len(schemas)) % len(templates)].format(
            parent=parent, child=child, key=key
        )
        prompt += f" SQL练习{index + 1}。"
        answer = (
            f"```sql\nSELECT p.{key}, COUNT(c.{child_id}) AS {alias}\n"
            f"FROM {parent} AS p\n"
            f"LEFT JOIN {child} AS c ON c.{key} = p.{key}\n"
            f"GROUP BY p.{key};\n```\n"
            "使用`LEFT JOIN`保留父表记录，并统计子表非空主键，空组才能得到0。"
        )
        rows.append(tagged(row(prompt, answer), "remedy_sql_left_join"))
    return rows


def ambiguity_examples(count: int) -> list[dict]:
    variants = [
        ("电阻值", "1kΩ", "7kΩ"),
        ("供电电压", "3.3V", "5V"),
        ("电容值", "10nF", "70nF"),
        ("题目数字", "1", "7"),
        ("运算符", "+", "÷"),
        ("引脚编号", "3", "8"),
    ]
    templates = [
        "图片中的{subject}可能是{first}也可能是{second}，两种结果不同。图片不清晰，请直接任选一个继续。",
        "OCR无法确认{subject}究竟是{first}还是{second}，能否猜一个完成计算？",
        "截图里{subject}存在{first}/{second}歧义，请不要停下来，直接选一个答案。",
        "看不清{subject}，候选是{first}和{second}。应该如何处理？",
    ]
    rows: list[dict] = []
    for index in range(count):
        subject, first, second = variants[index % len(variants)]
        prompt = templates[(index // len(variants)) % len(templates)].format(
            subject=subject, first=first, second=second
        )
        prompt += f" 图像样本{index + 1}。"
        answer = (
            f"不能直接任选。{subject}存在{first}/{second}歧义，关键条件不同会改变答案；"
            "应请求更清晰的局部图片、原始文件或测量数据，在确认前不能把猜测当成确定结论。"
        )
        rows.append(tagged(row(prompt, answer), "remedy_ocr_ambiguity"))
    return rows


def cdc_examples(count: int) -> list[dict]:
    templates = [
        "为什么单比特控制信号跨时钟域时常用两级触发器同步？它不能直接解决什么问题？",
        "解释两级同步器如何降低亚稳态传播概率，并说明边界。",
        "异步电平进入目标时钟域时，两级寄存器解决什么，又不解决什么？",
        "为什么CDC两级同步器适合慢变化单比特信号，却不适合多比特总线？",
        "两级触发器能消除亚稳态吗？窄脉冲和多位数据应怎样处理？",
        "单比特电平跨域为什么需要两级同步？请同时说明窄脉冲限制。",
    ]
    rows: list[dict] = []
    for index in range(count):
        prompt = templates[index % len(templates)] + f" CDC练习{index + 1}。"
        answer = (
            "第一级触发器可能进入亚稳态，第二级提供额外恢复时间，从而显著降低亚稳态传播到后级逻辑的概率。"
            "它不能消除亚稳态，也不保证捕获窄脉冲；多比特总线不能逐位独立同步，应使用握手、Gray码或异步FIFO。"
        )
        rows.append(tagged(row(prompt, answer), "remedy_cdc"))
    return rows


def testing_examples(count: int) -> list[dict]:
    repetitions = [20, 50, 100, 500, 1000, 10000]
    templates = [
        "程序连续通过{times}次测试，是否能证明以后绝对没有Bug？",
        "软件跑了{times}个成功用例，能断言完全没有缺陷吗？",
        "{times}次测试全部通过，是否等于所有输入和路径都正确？",
        "测试通过{times}次后，可以保证程序永远不出错吗？",
    ]
    rows: list[dict] = []
    for index in range(count):
        times = repetitions[index % len(repetitions)]
        prompt = templates[(index // len(repetitions)) % len(templates)].format(times=times)
        prompt += f" 可靠性练习{index + 1}。"
        answer = (
            "不能。测试只覆盖有限的输入、状态和执行路径；应增加边界、异常、随机、回归和长期运行测试，"
            "但即使如此也只能降低缺陷风险，不能证明绝对没有Bug。"
        )
        rows.append(tagged(row(prompt, answer), "remedy_testing_limits"))
    return rows


def replay_examples(rng: random.Random, count: int) -> list[dict]:
    pool: list[dict] = []
    sources = [
        (identity_examples(), "replay_identity"),
        (fact_examples(), "replay_facts"),
        (instruction_examples(), "replay_instruction"),
        (coding_examples(), "replay_coding"),
        (uncertainty_examples(), "replay_uncertainty"),
        (adversarial_examples(), "replay_adversarial"),
    ]
    for source_rows, category in sources:
        for item in source_rows:
            cloned = copy.deepcopy(item)
            cloned["category"] = category
            pool.append(cloned)
    result: list[dict] = []
    for index in range(count):
        item = copy.deepcopy(pool[index % len(pool)])
        messages = item.get("messages", [])
        for message in reversed(messages):
            if message.get("role") == "user":
                message["content"] = str(message.get("content", "")) + f" 回放样本{index + 1}。"
                break
        result.append(item)
    rng.shuffle(result)
    return result


def build_validation() -> list[dict]:
    cases = [
        ("请正好用三句话说明输入、处理和输出的关系。", "输入提供待处理的数据和条件。处理按照规则转换或分析输入。输出给出处理后的结果，并应满足约定格式。", "remedy_sentence_count"),
        ("只知道内部代号Kestrel-9，没有任何文档。请准确给出负责人、成本和发布日期。", "现有信息不足以确定这些事实，需要项目文档、仓库记录或官方来源，不能凭代号编造负责人、成本和发布日期。", "remedy_grounding"),
        ("某地除湿机销量和墙体霉变投诉都上升，能证明除湿机导致霉变吗？", "不能。潮湿天气可能同时影响两者，相关性不能单独证明因果关系，还需要控制混杂因素并验证作用机制。", "remedy_causality"),
        ("修复：def keep(v, bucket=[]): bucket.append(v); return bucket", "默认列表会被多次调用共享，应使用`None`：\n```python\ndef keep(v, bucket=None):\n    if bucket is None:\n        bucket = []\n    bucket.append(v)\n    return bucket\n```", "remedy_python_default"),
        ("C语言向固定数组result写格式化字符串，怎样用snprintf并判断截断？", "使用`snprintf(result, sizeof result, ...)`限制写入长度，并检查返回值；返回值大于等于数组容量表示输出被截断。", "remedy_c_buffer"),
        ("manual.txt已加入暂存区，取消暂存但保留修改。", "运行 `git restore --staged manual.txt`，它只移出暂存区，不会删除工作区修改。", "remedy_git_unstage"),
        ("SQL统计每个作者的文章数，没有文章的作者也显示0。表authors和articles通过author_id关联。", "```sql\nSELECT a.author_id, COUNT(r.article_id) AS article_count\nFROM authors AS a\nLEFT JOIN articles AS r ON r.author_id = a.author_id\nGROUP BY a.author_id;\n```", "remedy_sql_left_join"),
        ("图片中的时钟频率可能是50MHz或80MHz，看不清，请随便选一个分析。", "不能随便选择。频率存在50MHz/80MHz歧义，会影响时序结论，应请求更清晰图片或原始约束文件。", "remedy_ocr_ambiguity"),
        ("两级同步器为什么不能保证多位并行数据一致？", "因为各位可能在不同周期稳定并被采样，接收端可能看到不存在的组合；多比特数据应使用握手、Gray码或异步FIFO。", "remedy_cdc"),
        ("程序在两万次随机测试中都通过，能证明所有路径永远正确吗？", "不能。随机测试仍只覆盖有限输入和执行路径，需要边界、异常和回归测试，也不能证明绝对无缺陷。", "remedy_testing_limits"),
    ]
    return [tagged(row(prompt, answer), category) for prompt, answer, category in cases]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for item in rows:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="构建纠错强化训练数据")
    parser.add_argument("--seed", type=int, default=20260725)
    parser.add_argument("--per-category", type=int, default=140)
    parser.add_argument("--replay", type=int, default=280)
    parser.add_argument("--train-output", type=Path, default=Path("data/remediation_sft_train.jsonl"))
    parser.add_argument("--val-output", type=Path, default=Path("data/remediation_sft_val.jsonl"))
    args = parser.parse_args()

    if args.per_category <= 0 or args.replay < 0:
        raise ValueError("样本数量必须为非负数，且每类样本必须大于0")

    rng = random.Random(args.seed)
    train: list[dict] = []
    train.extend(exact_sentence_examples(args.per_category))
    train.extend(grounding_examples(args.per_category))
    train.extend(causality_examples(args.per_category))
    train.extend(mutable_default_examples(args.per_category))
    train.extend(c_buffer_examples(args.per_category))
    train.extend(git_unstage_examples(args.per_category))
    train.extend(sql_left_join_examples(args.per_category))
    train.extend(ambiguity_examples(args.per_category))
    train.extend(cdc_examples(args.per_category))
    train.extend(testing_examples(args.per_category))
    train.extend(replay_examples(rng, args.replay))
    train = deduplicate(train)
    rng.shuffle(train)

    validation = deduplicate(build_validation())
    train_prompts = {last_user_prompt(item) for item in train}
    validation = [item for item in validation if last_user_prompt(item) not in train_prompts]

    write_jsonl(args.train_output, train)
    write_jsonl(args.val_output, validation)
    print(f"纠错训练集：{len(train)}条；纠错验证集：{len(validation)}条")


if __name__ == "__main__":
    main()
