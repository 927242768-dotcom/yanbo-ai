"""构建彦博-v3兼容模型的专项攻坚数据集，并保留独立验证集。"""

from __future__ import annotations

import argparse
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
from performance_curriculum import tag_many, tagged


def deduplicate(rows: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for item in rows:
        key = json.dumps(item.get("messages", []), ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def ratio_examples(rng: random.Random, count: int) -> list[dict]:
    rows: list[dict] = []
    names = [("甲", "乙"), ("男生", "女生"), ("红笔", "蓝笔"), ("A箱", "B箱")]
    while len(rows) < count:
        a, b = rng.randint(1, 9), rng.randint(1, 9)
        unit = rng.randint(2, 20)
        total = (a + b) * unit
        if (a, b, total) == (3, 5, 40):
            continue
        left, right = rng.choice(names)
        prompt = rng.choice([
            f"{left}和{right}的数量比为{a}:{b}，总数是{total}，分别有多少？",
            f"共有{total}个，按{a}:{b}分给{left}与{right}，两者各得多少？",
            f"已知{left}:{right}={a}:{b}，并且合计{total}，求两部分数量。",
        ])
        answer = (
            f"总份数是{a+b}，每份是{total}÷{a+b}={unit}；"
            f"{left}有{a*unit}，{right}有{b*unit}。"
        )
        rows.append(tagged(row(prompt, answer), "focus_ratio"))
    return rows


def missing_average_examples(rng: random.Random, count: int) -> list[dict]:
    rows: list[dict] = []
    while len(rows) < count:
        amount = rng.choice([4, 5, 6])
        mean = rng.randint(5, 30)
        known = [rng.randint(1, 35) for _ in range(amount - 1)]
        missing = mean * amount - sum(known)
        if amount == 5 and mean == 12 and known == [8, 10, 13, 14]:
            continue
        rendered = "、".join(map(str, known))
        prompt = rng.choice([
            f"{amount}个数的平均数是{mean}，已知其中{amount-1}个数为{rendered}，剩下一个数是多少？",
            f"一组共有{amount}个数据，平均值为{mean}，除一个数外其余是{rendered}，求缺少的数据。",
        ])
        answer = (
            f"总和应为{mean}×{amount}={mean*amount}，已知数之和为{sum(known)}，"
            f"所以缺少的数是{mean*amount}-{sum(known)}={missing}。"
        )
        rows.append(tagged(row(prompt, answer), "focus_average"))
    return rows


def mutable_default_examples(rng: random.Random, count: int) -> list[dict]:
    functions = ["append_value", "collect_item", "remember", "add_record", "push_entry"]
    parameters = ["items", "values", "records", "result", "cache"]
    rows: list[dict] = []
    for index in range(count):
        function = functions[index % len(functions)]
        parameter = parameters[(index // len(functions)) % len(parameters)]
        prefix = rng.choice(["修复", "解释并修复", "给出正确写法来避免"])
        prompt = (
            f"{prefix}Python共享可变默认参数问题："
            f"def {function}(x, {parameter}=[]): {parameter}.append(x); return {parameter}"
        )
        answer = (
            "默认列表只在函数定义时创建一次，会被后续调用共享。应使用`None`作为哨兵：\n"
            f"```python\ndef {function}(x, {parameter}=None):\n"
            f"    if {parameter} is None:\n        {parameter} = []\n"
            f"    {parameter}.append(x)\n    return {parameter}\n```"
        )
        rows.append(tagged(row(prompt, answer), "focus_python"))
    return rows


def git_unstage_examples(rng: random.Random, count: int) -> list[dict]:
    files = ["config.json", "main.py", "notes.md", "src/app.c", "docs/guide.md", "Makefile"]
    rows: list[dict] = []
    for index in range(count):
        filename = files[index % len(files)]
        prompt = rng.choice([
            f"{filename}已经git add，怎样取消暂存但保留工作区内容？",
            f"我误把{filename}加入暂存区，不想丢修改，应该执行什么命令？",
            f"只撤销{filename}的暂存状态，文件修改继续保留。给出Git命令。",
        ])
        answer = (
            f"运行 `git restore --staged {filename}`。"
            "它只把文件移出暂存区，不会删除工作区修改。"
        )
        rows.append(tagged(row(prompt, answer), "focus_git"))
    return rows


def sql_left_join_examples(rng: random.Random, count: int) -> list[dict]:
    schemas = [
        ("teams", "members", "team_id", "member_id", "member_count"),
        ("projects", "tasks", "project_id", "task_id", "task_count"),
        ("categories", "products", "category_id", "product_id", "product_count"),
        ("classes", "students", "class_id", "student_id", "student_count"),
    ]
    rows: list[dict] = []
    for index in range(count):
        parent, child, key, child_id, alias = schemas[index % len(schemas)]
        prompt = rng.choice([
            f"写SQL统计每个{parent}记录对应的{child}数量，没有{child}的也必须显示0。",
            f"表{parent}与{child}通过{key}关联，查询每个{key}的{child}数量并保留空组。",
        ])
        answer = (
            f"```sql\nSELECT p.{key}, COUNT(c.{child_id}) AS {alias}\n"
            f"FROM {parent} AS p\nLEFT JOIN {child} AS c ON c.{key} = p.{key}\n"
            f"GROUP BY p.{key};\n```\n"
            f"使用`LEFT JOIN`保留父表记录，并统计子表非空主键，空组才能得到0。"
        )
        rows.append(tagged(row(prompt, answer), "focus_sql"))
    return rows


def cdc_examples(rng: random.Random, count: int) -> list[dict]:
    rows: list[dict] = []
    prompts = [
        "单比特电平信号跨时钟域为什么常串联两级触发器？它的边界是什么？",
        "解释两级同步器如何降低亚稳态传播概率，并说明不能直接同步哪类数据。",
        "异步控制信号进入目标时钟域时，两级寄存器同步解决什么问题，又不解决什么问题？",
        "为什么CDC中的两级触发器适合慢变化单比特信号，却不适合多比特总线？",
    ]
    answers = [
        "第一级触发器可能进入亚稳态，第二级提供额外恢复时间，从而降低亚稳态传播到后级逻辑的概率。它适合慢变化单比特电平，不保证捕获窄脉冲，也不能保证多比特总线各位一致。",
        "两级同步器不能消除亚稳态，只能显著降低其传播概率。多比特数据应使用握手、Gray码或异步FIFO，窄脉冲还需要展宽或握手。",
    ]
    for index in range(count):
        prompt = prompts[index % len(prompts)] + rng.choice(["", "请先给结论。", "回答要准确简洁。"])
        answer = answers[index % len(answers)]
        rows.append(tagged(row(prompt, answer), "focus_cdc"))
    return rows


def grounding_and_logic_examples(rng: random.Random, count: int) -> list[dict]:
    rows: list[dict] = []
    unknown_entities = ["SilverLake", "ProjectNova", "芯片XK-27", "内部计划Orion", "设备原型P9"]
    causal_pairs = [
        ("冷饮销量", "中暑人数", "高温"),
        ("雨衣销量", "道路拥堵", "降雨"),
        ("空调使用量", "用电故障", "炎热天气"),
        ("搜索量", "产品退货", "促销活动"),
    ]
    for index in range(count):
        if index % 2 == 0:
            entity = unknown_entities[index % len(unknown_entities)]
            prompt = rng.choice([
                f"我只给出名称{entity}，请说出它准确的负责人、成本和发布日期。",
                f"没有附加资料。请确定{entity}的团队、预算与发布时间。",
            ])
            answer = (
                "现有信息不足以确定这些事实。需要项目文档、仓库记录或官方来源；"
                "不能仅凭名称编造负责人、预算和发布日期。"
            )
            category = "focus_grounding"
        else:
            first, second, common = causal_pairs[index % len(causal_pairs)]
            prompt = f"某地{first}和{second}同时上升，能直接证明前者导致后者吗？"
            answer = (
                f"不能。两者可能都受到{common}等共同因素影响；相关性不能单独证明因果关系，"
                "还需要时间顺序、机制、对照和混杂因素控制。"
            )
            category = "focus_logic"
        rows.append(tagged(row(prompt, answer), category))
    return rows


def ambiguity_and_testing_examples(rng: random.Random, count: int) -> list[dict]:
    rows: list[dict] = []
    ambiguities = [
        ("电容值", "10nF", "70nF"),
        ("电阻值", "2kΩ", "7kΩ"),
        ("题目数字", "1", "7"),
        ("运算符", "+", "÷"),
    ]
    for index in range(count):
        if index % 2 == 0:
            subject, first, second = ambiguities[index % len(ambiguities)]
            prompt = (
                f"图片中的{subject}可能是{first}也可能是{second}，两种结果不同。"
                "图片不清晰，请直接任选一个继续。"
            )
            answer = (
                f"不能直接任选。{subject}存在{first}/{second}歧义，关键条件不同会改变答案；"
                "应请求更清晰的局部图片或原始数据。"
            )
            category = "focus_ambiguity"
        else:
            times = rng.choice([20, 50, 100, 500])
            prompt = f"程序连续通过{times}次测试，是否能证明以后绝对没有Bug？"
            answer = (
                "不能。测试只覆盖有限输入、状态和执行路径；应增加边界、异常、随机、回归和长期测试，"
                "但即使如此也不能证明绝对无缺陷。"
            )
            category = "focus_testing"
        rows.append(tagged(row(prompt, answer), category))
    return rows


def exact_sentence_examples(rng: random.Random, count: int) -> list[dict]:
    concepts = [
        ("训练集、验证集和测试集", ["训练集用于更新模型参数。", "验证集用于选择配置并监控泛化。", "测试集用于最终独立评估，不能参与调参。"]),
        ("进程、线程和协程", ["进程通常拥有独立地址空间。", "线程共享进程资源并由操作系统调度。", "协程通常在用户态协作切换，适合大量等待任务。"]),
        ("源码、构建缓存和发布包", ["源码是需要长期维护和版本控制的输入。", "构建缓存可以重新生成，通常不应进入仓库。", "发布包是交付产物，应按版本保存并校验。"]),
        ("训练损失、验证损失和真实任务得分", ["训练损失反映模型对训练样本的拟合。", "验证损失用于观察未参与更新数据上的泛化趋势。", "真实任务得分才直接反映目标能力，三者不能互相替代。"]),
    ]
    rows: list[dict] = []
    for index in range(count):
        concept, sentences = concepts[index % len(concepts)]
        prompt = rng.choice([
            f"请恰好用三句话说明{concept}的区别。",
            f"解释{concept}，只能写三句话。",
            f"关于{concept}，输出正好三句，不要前言。",
        ])
        rows.append(tagged(row(prompt, "".join(sentences)), "focus_sentence_count"))
    return rows


def replay_examples(rng: random.Random, count: int) -> list[dict]:
    pool: list[dict] = []
    pool.extend(tag_many(identity_examples(), "replay_identity"))
    pool.extend(tag_many(fact_examples(), "replay_facts"))
    pool.extend(tag_many(instruction_examples(), "replay_instruction"))
    pool.extend(tag_many(coding_examples(), "replay_coding"))
    pool.extend(tag_many(uncertainty_examples(), "replay_uncertainty"))
    pool.extend(tag_many(adversarial_examples(), "replay_adversarial"))
    rows: list[dict] = []
    for _ in range(count):
        source = rng.choice(pool)
        rows.append(json.loads(json.dumps(source, ensure_ascii=False)))
    return rows


def build_validation() -> list[dict]:
    cases = [
        ("丁和戊数量比为4:7，总数77，分别是多少？", "总份数是11，每份是7；丁有28，戊有49。", "focus_ratio"),
        ("六个数平均为15，已知五个数是8、11、14、18、20，缺少的数是多少？", "总和应为15×6=90，已知数之和为71，所以缺少的数是19。", "focus_average"),
        ("修复：def stash(v, data=[]): data.append(v); return data", "默认列表会在调用之间共享，应改为：\n```python\ndef stash(v, data=None):\n    if data is None:\n        data = []\n    data.append(v)\n    return data\n```", "focus_python"),
        ("manual.md已经加入暂存区，取消暂存但保留修改。", "运行 `git restore --staged manual.md`，工作区修改会保留。", "focus_git"),
        ("查询每个仓库及其库存记录数，没有库存记录的仓库也显示0。表warehouses和stocks通过warehouse_id关联。", "```sql\nSELECT w.warehouse_id, COUNT(s.stock_id) AS stock_count\nFROM warehouses AS w\nLEFT JOIN stocks AS s ON s.warehouse_id = w.warehouse_id\nGROUP BY w.warehouse_id;\n```", "focus_sql"),
        ("两级同步器为什么不能保证多位并行数据一致？", "因为每一位可能在不同周期稳定并被采样，接收端可能看到不存在的组合；多比特数据应使用握手、Gray码或异步FIFO。", "focus_cdc"),
        ("只知道代号Delta，没有任何文档，能准确说出负责人和成本吗？", "不能。现有信息不足，需要可核验文档或官方记录，不能凭代号编造负责人和成本。", "focus_grounding"),
        ("防晒霜销量和空调故障都增加，能证明防晒霜导致空调故障吗？", "不能。高温可能同时影响两者，相关性不能直接证明因果关系。", "focus_logic"),
        ("图中标注可能是3.3V或5V，看不清，请随便选一个。", "不能随便选择。电压存在3.3V/5V歧义，会影响结论，应请求更清晰图片或测量数据。", "focus_ambiguity"),
        ("软件通过一千次测试，能证明绝对没有缺陷吗？", "不能。测试覆盖有限输入和路径，只能降低风险，不能证明绝对无缺陷。", "focus_testing"),
        ("请正好用三句话解释需求、设计和测试的关系。", "需求定义系统要解决的问题和验收目标。设计把需求转化为结构、接口和实现方案。测试依据需求验证实现，并反馈设计缺陷。", "focus_sentence_count"),
    ]
    return [tagged(row(prompt, answer), category) for prompt, answer, category in cases]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for item in rows:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="构建专项攻坚训练数据")
    parser.add_argument("--seed", type=int, default=20260725)
    parser.add_argument("--train-output", type=Path, default=Path("data/focus_sft_train.jsonl"))
    parser.add_argument("--val-output", type=Path, default=Path("data/focus_sft_val.jsonl"))
    args = parser.parse_args()

    rng = random.Random(args.seed)
    train: list[dict] = []
    train.extend(ratio_examples(rng, 180))
    train.extend(missing_average_examples(rng, 150))
    train.extend(mutable_default_examples(rng, 100))
    train.extend(git_unstage_examples(rng, 90))
    train.extend(sql_left_join_examples(rng, 100))
    train.extend(cdc_examples(rng, 100))
    train.extend(grounding_and_logic_examples(rng, 160))
    train.extend(ambiguity_and_testing_examples(rng, 140))
    train.extend(exact_sentence_examples(rng, 100))
    train.extend(replay_examples(rng, 220))
    train = deduplicate(train)
    rng.shuffle(train)

    validation = deduplicate(build_validation())
    train_prompts = {
        next(
            str(message.get("content", ""))
            for message in reversed(item["messages"])
            if message.get("role") == "user"
        )
        for item in train
    }
    validation = [
        item
        for item in validation
        if next(
            str(message.get("content", ""))
            for message in reversed(item["messages"])
            if message.get("role") == "user"
        )
        not in train_prompts
    ]
    write_jsonl(args.train_output, train)
    write_jsonl(args.val_output, validation)
    print(f"专项训练集：{len(train)}条；专项验证集：{len(validation)}条")


if __name__ == "__main__":
    main()
