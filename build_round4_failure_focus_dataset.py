"""构建彦博-v3第4轮失败簇专项数据。

该数据集根据独立泛化基线暴露的失败类型设计，但不复制评测题目。
所有数字、实体、代码变量、文件名和表结构均使用独立生成空间。
"""

from __future__ import annotations

import argparse
import copy
import json
import random
from pathlib import Path

from build_quality_dataset import row
from console_utils import configure_utf8_console


def tagged(item: dict, category: str) -> dict:
    item["category"] = category
    return item


def prompt_of(item: dict) -> str:
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


def _is_prime(value: int) -> bool:
    if value < 2:
        return False
    divisor = 2
    while divisor * divisor <= value:
        if value % divisor == 0:
            return False
        divisor += 1
    return True


def direct_answer_examples(count: int) -> list[dict]:
    rows: list[dict] = []
    title_sources = [
        ("发布前先执行回归测试", "发布前回归测试"),
        ("每天备份不可再生的项目文件", "项目文件每日备份"),
        ("提交代码前检查格式和测试", "提交前检查"),
        ("图片模糊时不要猜测关键参数", "模糊参数不猜测"),
        ("训练候选退化时立即回滚", "退化候选立即回滚"),
    ]
    for index in range(count):
        kind = index % 3
        if kind == 0:
            a = 11 + (index * 7) % 79
            b = 2 + (index * 5) % 17
            prompt = f"只回答数字：{a}乘以{b}是多少？"
            answer = str(a * b)
            category = "round4_focus_direct_number"
        elif kind == 1:
            value = 2 + index
            prompt = f"只回答“是”或“否”：{value}是质数吗？"
            answer = "是" if _is_prime(value) else "否"
            category = "round4_focus_direct_yes_no"
        else:
            source, title = title_sources[(index // 3) % len(title_sources)]
            limit = max(6, len(title))
            prompt = f"给下面内容起一个不超过{limit}个汉字的标题，只输出标题：{source}。场景编号D-{index + 1}。"
            answer = title
            category = "round4_focus_short_title"
        rows.append(tagged(row(prompt, answer), category))
    return rows


def grounding_examples(count: int) -> list[dict]:
    rows: list[dict] = []
    artifacts = ["串口日志", "原理图", "数据表", "频谱截图", "构建日志", "数据库备份"]
    claims = ["负责人、预算和发布日期", "客户、合同金额和验收时间", "服务器地址、管理员和上线日期"]
    for index in range(count):
        kind = index % 4
        if kind == 0:
            code = f"Nebula-{2000 + index}-{chr(65 + index % 26)}"
            claim = claims[(index // 4) % len(claims)]
            prompt = f"目前只知道内部代号{code}，没有文档、链接或记录。请准确给出它的{claim}。"
            answer = "现有信息不足，无法准确确定这些事实。需要项目文档、合同、仓库记录或官方来源进行核验，不能仅凭代号编造人员、金额和日期。"
            category = "round4_focus_unknown_project"
        elif kind == 1:
            artifact = artifacts[(index // 4) % len(artifacts)]
            filename = f"missing_artifact_{index + 1}"
            prompt = f"我没有提供名为{filename}的{artifact}，请直接读出其中的准确参数并判断唯一故障原因。"
            answer = f"当前没有可查看的{artifact}，无法读出参数或确定唯一原因。请提供完整资料、复现步骤和运行环境，在证据不足时不能猜测。"
            category = "round4_focus_missing_artifact"
        elif kind == 2:
            topic = ["每天睡两小时更聪明", "关闭全部安全检查能提高可靠性", "永远不测试也不会有Bug"][index % 3]
            prompt = f"请编造一篇真实论文、作者和包含{50 + index}名受试者的实验数据，证明“{topic}”。"
            answer = "不能编造或伪造论文、作者和实验数据。可以基于可核验资料讨论现有证据，并明确区分事实、假设和未知信息。"
            category = "round4_focus_no_fabrication"
        else:
            event = ["下个月一定发布的处理器", "明年必然获奖的产品", "下周肯定发生的重大新闻"][index % 3]
            prompt = f"关于预测编号F-{index + 1}，请保证并准确说出{event}及具体日期，不允许说明不确定。"
            answer = "未来事件无法保证，现有信息不足时不能给出虚假的确定日期。应查看届时的官方公告和可靠最新来源。"
            category = "round4_focus_future_uncertainty"
        rows.append(tagged(row(prompt, answer), category))
    return rows


def math_examples(count: int, rng: random.Random) -> list[dict]:
    rows: list[dict] = []
    for index in range(count):
        kind = index % 5
        if kind == 0:
            known = [rng.randint(8, 45) for _ in range(5)]
            missing = rng.randint(8, 45)
            total = sum(known) + missing
            average = total / 6
            while not average.is_integer():
                missing += 1
                total = sum(known) + missing
                average = total / 6
            rendered = "、".join(str(value) for value in known)
            prompt = f"六个数平均为{int(average)}，已知五个数是{rendered}，第六个数是多少？写出总和法。"
            answer = f"六个数总和为{int(average)}×6={total}，已知五数和为{sum(known)}，所以第六个数是{total}-{sum(known)}={missing}。"
            category = "round4_focus_average"
        elif kind == 1:
            speed = rng.choice([36, 48, 54, 60, 72, 84, 90, 96])
            hours = rng.randint(1, 5)
            minutes = rng.choice([15, 30, 45])
            time_value = hours + minutes / 60
            distance = speed * time_value
            prompt = f"速度为每小时{speed}千米，行驶{hours}小时{minutes}分钟，路程是多少？"
            answer = f"{hours}小时{minutes}分钟等于{time_value:g}小时，路程={speed}×{time_value:g}={distance:g}千米。"
            category = "round4_focus_rate"
        elif kind == 2:
            pairs = [(0.1, 0.2), (0.2, 0.4), (0.7, 0.1), (0.3, 0.6)]
            languages = ["Python", "C", "Java", "JavaScript", "Rust", "C++"]
            a, b = pairs[(index // 5) % len(pairs)]
            language = languages[(index // 7) % len(languages)]
            prompt = f"在{language}示例FP-{index + 1}中，为什么浮点运算{a}+{b}可能出现末尾微小误差？"
            answer = "许多十进制小数不能用有限位二进制浮点数精确表示，存储时只能取近似值，运算后会出现很小的舍入误差。需要精确十进制时可使用Decimal或整数缩放。"
            category = "round4_focus_float"
        elif kind == 3:
            numerator = 1 + (index * 11) % 1000
            prompt = f"计算{numerator}除以0，并说明数学上是否有有限结果。"
            answer = "除数不能为零，这个除法在普通实数算术中没有定义，也不存在可作为结果的有限数；不能直接说等于无穷大。"
            category = "round4_focus_div_zero"
        else:
            x = rng.randint(3, 50)
            offset = rng.randint(2, 15)
            multiplier = rng.randint(2, 9)
            result = (x + offset) * multiplier
            prompt = f"一个数先加{offset}再乘{multiplier}得到{result}，求这个数并写出逆运算。"
            answer = f"先算{result}÷{multiplier}={x+offset}，再算{x+offset}-{offset}={x}，所以这个数是{x}。"
            category = "round4_focus_equation"
        rows.append(tagged(row(prompt, answer), category))
    return rows


def logic_complexity_examples(count: int) -> list[dict]:
    rows: list[dict] = []
    systems = ["桌面程序", "固件", "网页服务", "数据库工具", "移动应用", "驱动程序"]
    for index in range(count):
        kind = index % 4
        system = f"{systems[index % len(systems)]}-{index + 1}"
        if kind == 0:
            prompt = f"{system}已经通过编译。能否据此断言它一定正确运行且逻辑正确？"
            answer = "不能。通过编译通常只是运行的必要前提之一，不是正确运行的充分条件；链接、依赖、权限、输入、运行时异常和逻辑错误仍可能导致失败。"
            category = "round4_focus_compile_not_sufficient"
        elif kind == 1:
            variable = f"n_{index + 1}"
            prompt = f"外层循环执行{variable}次，内层第i次执行i次，循环体为常数操作，时间复杂度是什么？"
            answer = f"总操作次数为1+2+…+{variable}={variable}({variable}+1)/2，最高次项与{variable}²成正比，所以时间复杂度是O(n²)。"
            category = "round4_focus_triangular_complexity"
        elif kind == 2:
            first, second, common = [
                ("制冷设备销量", "电网报警次数", "高温"),
                ("雨具销量", "交通拥堵", "降雨"),
                ("药品销量", "门诊人数", "流行疾病"),
                ("搜索次数", "退款数量", "促销活动"),
            ][(index // 4) % 4]
            location = ["东城区", "高新区", "滨海区", "大学城", "工业园"][index % 5]
            prompt = f"{2020 + index % 7}年{location}的{first}与{second}同步上升，能直接证明前者造成后者吗？"
            answer = f"不能。{common}等共同因素可能同时影响两者；相关性不能单独证明因果，需要控制混杂因素并验证时间顺序和作用机制。"
            category = "round4_focus_causality"
        else:
            times = 100 + index * 97
            prompt = f"{system}连续通过{times}次测试，能证明所有输入、环境和路径下永远没有Bug吗？"
            answer = "不能。测试只能覆盖有限输入、状态、路径和环境；应补充边界、异常、并发、回归和长期测试，但仍不能证明绝对无缺陷。"
            category = "round4_focus_test_limits"
        rows.append(tagged(row(prompt, answer), category))
    return rows


def python_c_examples(count: int) -> list[dict]:
    rows: list[dict] = []
    for index in range(count):
        kind = index % 7
        suffix = index + 1
        if kind == 0:
            fn = f"put_{suffix}"
            param = f"cache_{suffix}"
            prompt = f"修复共享默认字典：def {fn}(k, v, {param}={{}}): {param}[k]=v; return {param}"
            answer = f"默认字典会在多次调用间共享，应使用`None`：\n```python\ndef {fn}(k, v, {param}=None):\n    if {param} is None:\n        {param} = {{}}\n    {param}[k] = v\n    return {param}\n```"
            category = "round4_focus_python_default_dict"
        elif kind == 1:
            fn = f"find_max_{suffix}"
            prompt = f"写Python函数`{fn}`求整数列表最大值，不调用max；空列表抛ValueError。"
            answer = f"```python\ndef {fn}(values: list[int]) -> int:\n    if not values:\n        raise ValueError(\"列表不能为空\")\n    result = values[0]\n    for value in values[1:]:\n        if value > result:\n            result = value\n    return result\n```"
            category = "round4_focus_python_manual_max"
        elif kind == 2:
            size = 2 + index % 6
            variable = f"rows_{suffix}"
            prompt = f"解释并修复：{variable}=[[0]*3]*{size}；修改第一行时所有行一起变化。"
            answer = f"乘法复制的是同一个内部列表引用。应创建独立列表：\n```python\n{variable} = [[0] * 3 for _ in range({size})]\n```"
            category = "round4_focus_python_alias"
        elif kind == 3:
            variable = f"data_{suffix}"
            prompt = f"修复越界：{variable}=[1,2,3]; for i in range(len({variable})+1): print({variable}[i])"
            answer = f"循环上界多了1。可直接遍历：\n```python\n{variable} = [1, 2, 3]\nfor value in {variable}:\n    print(value)\n```"
            category = "round4_focus_python_off_by_one"
        elif kind == 4:
            buffer_name = f"out_{suffix}"
            capacity = 32 + (index % 8) * 16
            prompt = f"C语言有`char {buffer_name}[{capacity}]`，怎样替代sprintf并检查格式化输出是否截断？"
            answer = f"使用`snprintf({buffer_name}, sizeof {buffer_name}, ...)`，检查返回值：小于0表示失败，大于等于`sizeof {buffer_name}`表示截断。"
            category = "round4_focus_c_snprintf"
        elif kind == 5:
            pointer = f"items_{suffix}"
            count_name = f"count_{suffix}"
            prompt = f"C语言执行`malloc({count_name} * sizeof *{pointer})`前后需要检查什么？"
            answer = f"先检查`{count_name} > SIZE_MAX / sizeof *{pointer}`以防乘法溢出，再检查`malloc`返回值是否为`NULL`；使用完成后调用`free({pointer})`。"
            category = "round4_focus_c_malloc"
        else:
            pointer = f"ptr_{suffix}"
            prompt = f"为什么`free({pointer})`后继续访问`*{pointer}`错误？"
            answer = f"释放后内存不再有效，继续访问属于释放后使用并产生未定义行为。不得再解引用，可执行`{pointer} = NULL;`降低误用风险。"
            category = "round4_focus_c_use_after_free"
        rows.append(tagged(row(prompt, answer), category))
    return rows


def tools_sql_examples(count: int) -> list[dict]:
    rows: list[dict] = []
    for index in range(count):
        kind = index % 5
        suffix = index + 1
        if kind == 0:
            filename = f"src/module_{suffix}.py"
            prompt = f"{filename}已经git add，取消暂存但保留工作区修改，给出命令。"
            answer = f"`git restore --staged {filename}`"
            category = "round4_focus_git_unstage"
        elif kind == 1:
            filename = f"docs/note_{suffix}.md"
            prompt = f"怎样查看已经暂存但尚未提交的{filename}差异？"
            answer = f"运行 `git diff --cached -- {filename}`，也可以使用等价的`git diff --staged -- {filename}`。"
            category = "round4_focus_git_cached_diff"
        elif kind == 2:
            term = ["timeout", "ERROR", "disconnect", "overflow", "failed"][index % 5]
            directory = f"./logs/service_{suffix}"
            prompt = f"Linux中递归搜索目录{directory}下所有.log文件里包含{term}的行，并显示行号。"
            answer = f"```bash\ngrep -R --include='*.log' -n '{term}' {directory}\n```"
            category = "round4_focus_linux_grep"
        elif kind == 3:
            parent = f"groups_{suffix}"
            child = f"entries_{suffix}"
            key = f"group_id_{suffix}"
            child_id = f"entry_id_{suffix}"
            prompt = f"SQL统计每个{parent}的{child}数量，没有子记录也显示0；通过{key}关联。"
            answer = f"```sql\nSELECT p.{key}, COUNT(c.{child_id}) AS child_count\nFROM {parent} AS p\nLEFT JOIN {child} AS c ON c.{key} = p.{key}\nGROUP BY p.{key};\n```"
            category = "round4_focus_sql_left_join"
        else:
            child = f"records_{suffix}"
            prompt = f"LEFT JOIN后为什么`COUNT(*)`可能让没有{child}的父项显示为1？"
            answer = f"因为LEFT JOIN会为无匹配的父项保留一行，COUNT(*)会统计该行。应统计子表仅在匹配时非空的列，例如`COUNT({child}.id)`。"
            category = "round4_focus_sql_count"
        rows.append(tagged(row(prompt, answer), category))
    return rows


def engineering_writing_examples(count: int) -> list[dict]:
    rows: list[dict] = []
    for index in range(count):
        kind = index % 5
        suffix = index + 1
        if kind == 0:
            prompt = f"单比特控制信号ctrl_{suffix}从clk_a跨到clk_b，为什么使用两级同步器？边界是什么？"
            answer = "第一级可能进入亚稳态，第二级提供额外恢复时间以降低亚稳态传播概率。它不保证捕获窄脉冲，也不适合逐位同步多比特总线；这些场景应使用脉冲展宽、握手、Gray码或异步FIFO。"
            category = "round4_focus_fpga_cdc"
        elif kind == 1:
            prompt = f"时钟域clk_{suffix}的异步复位rst_{suffix}为什么要同步释放？"
            answer = "异步置位可立即复位，同步释放让撤销动作对齐目标时钟，降低恢复时间违例和不同寄存器在不同周期退出复位的风险。每个时钟域应分别同步释放。"
            category = "round4_focus_fpga_reset"
        elif kind == 2:
            prompt = f"总线data_{suffix}[15:0]跨时钟域时，为什么不能每位分别接两级同步器？"
            answer = "各位可能在不同周期稳定并被采样，接收端会看到源端从未出现的组合。应使用握手保持、Gray码或异步FIFO保证多比特数据一致性。"
            category = "round4_focus_fpga_bus"
        elif kind == 3:
            prompt = f"把“你到底什么时候修好模块{suffix}”改得礼貌专业，只输出一句话。"
            answer = f"麻烦你同步一下模块{suffix}的修复进度，并说明预计完成时间，谢谢。"
            category = "round4_focus_writing_progress"
        else:
            prompt = f"把“版本{suffix}的设计完全不行”改成专业、可执行的一句话，只输出成品。"
            answer = f"版本{suffix}目前尚未满足关键目标，建议重新核对约束、定位主要缺口并制定具体优化方案。"
            category = "round4_focus_writing_critique"
        rows.append(tagged(row(prompt, answer), category))
    return rows


def load_replay(path: Path, count: int, rng: random.Random) -> list[dict]:
    if count <= 0 or not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rng.shuffle(rows)
    result: list[dict] = []
    for item in rows[: min(count, len(rows))]:
        cloned = copy.deepcopy(item)
        cloned["category"] = "round4_focus_replay_" + str(item.get("category", "general"))
        result.append(cloned)
    return result


def validation_rows() -> list[dict]:
    cases = [
        ("只回答数字：23乘以8是多少？", "184", "round4_focus_direct_number"),
        ("只回答“是”或“否”：21是质数吗？", "否", "round4_focus_direct_yes_no"),
        ("只有代号Quartz-91，没有任何资料，请给出准确负责人和预算。", "现有信息不足，无法确定负责人和预算，需要文档或官方记录核验，不能凭代号编造。", "round4_focus_unknown_project"),
        ("五个数平均为34，已知四个数为22、31、36、41，第五个是多少？", "五数总和为170，已知四数和为130，所以第五个数是40。", "round4_focus_average"),
        ("速度每小时88千米，行驶1小时45分钟，路程是多少？", "1小时45分钟等于1.75小时，路程为88×1.75=154千米。", "round4_focus_rate"),
        ("为什么0.4+0.2在二进制浮点中可能有微小误差？", "许多十进制小数不能用有限位二进制浮点数精确表示，因此存储和运算会产生微小舍入误差。", "round4_focus_float"),
        ("程序已经编译成功，能证明它一定正确运行吗？", "不能。编译成功不是正确运行的充分条件，仍可能存在依赖、运行时异常和逻辑错误。", "round4_focus_compile_not_sufficient"),
        ("外层n次，内层第i次执行i次，复杂度是什么？", "总次数为n(n+1)/2，所以时间复杂度是O(n²)。", "round4_focus_triangular_complexity"),
        ("修复：def set_value(k,v,memo={}): memo[k]=v; return memo", "应使用None：\n```python\ndef set_value(k, v, memo=None):\n    if memo is None:\n        memo = {}\n    memo[k] = v\n    return memo\n```", "round4_focus_python_default_dict"),
        ("C语言固定数组dst中格式化输出，怎样判断snprintf截断？", "检查snprintf返回值；若返回值大于等于数组容量，表示输出被截断。", "round4_focus_c_snprintf"),
        ("app/settings.py已暂存，取消暂存但保留修改。", "`git restore --staged app/settings.py`", "round4_focus_git_unstage"),
        ("为什么多比特总线不能逐位使用两级同步器？", "各位可能在不同周期被采样，产生源端不存在的组合；应使用握手、Gray码或异步FIFO。", "round4_focus_fpga_bus"),
        ("把“这个实现太差了”改成专业的一句话。", "当前实现仍有较大优化空间，建议先定位关键缺口并逐项改进。", "round4_focus_writing_critique"),
    ]
    return [tagged(row(prompt, answer), category) for prompt, answer, category in cases]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for item in rows:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="构建第4轮失败簇专项数据")
    parser.add_argument("--seed", type=int, default=20260726)
    parser.add_argument("--per-group", type=int, default=260)
    parser.add_argument("--replay", type=int, default=700)
    parser.add_argument("--replay-source", type=Path, default=Path("data/round4_generalization_train.jsonl"))
    parser.add_argument("--train-output", type=Path, default=Path("data/round4_failure_focus_train.jsonl"))
    parser.add_argument("--val-output", type=Path, default=Path("data/round4_failure_focus_val.jsonl"))
    args = parser.parse_args()
    if args.per_group <= 0 or args.replay < 0:
        raise ValueError("样本数量参数无效")

    rng = random.Random(args.seed)
    train: list[dict] = []
    train.extend(direct_answer_examples(args.per_group))
    train.extend(grounding_examples(args.per_group))
    train.extend(math_examples(args.per_group * 2, rng))
    train.extend(logic_complexity_examples(args.per_group))
    train.extend(python_c_examples(args.per_group * 2))
    train.extend(tools_sql_examples(args.per_group))
    train.extend(engineering_writing_examples(args.per_group))
    train.extend(load_replay(args.replay_source, args.replay, rng))
    train = deduplicate(train)
    rng.shuffle(train)

    validation = deduplicate(validation_rows())
    train_prompts = {prompt_of(item) for item in train}
    validation = [item for item in validation if prompt_of(item) not in train_prompts]
    write_jsonl(args.train_output, train)
    write_jsonl(args.val_output, validation)
    print(f"失败簇训练集：{len(train)}条")
    print(f"失败簇验证集：{len(validation)}条")


if __name__ == "__main__":
    main()
