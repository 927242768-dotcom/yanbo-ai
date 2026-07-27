"""构建彦博-v3第5轮高可靠课程数据集。

第5轮在第4轮广覆盖课程上增加：
- 更严格的证据边界与拒绝编造；
- 三项比例、连续折扣、单位换算等数量推理；
- 欧姆定律、串并联、分压、ADC、RC、PWM和定时器等电子/嵌入式计算；
- 旧能力回放，降低灾难性遗忘。

独立鲁棒性评测中的题目不会被复制到本数据集。
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
from pathlib import Path

from build_quality_dataset import row
from build_round4_generalization_dataset import (
    ambiguity_examples,
    c_and_system_examples,
    deduplicate,
    engineering_examples as round4_engineering_examples,
    git_linux_sql_examples,
    grounding_examples,
    instruction_constraint_examples,
    logic_examples,
    memory_examples_round4,
    python_examples,
    replay_examples,
    tagged,
    user_prompt,
    write_jsonl,
    writing_examples,
)
from console_utils import configure_utf8_console


def render(value: float) -> str:
    if math.isclose(value, round(value), rel_tol=1e-12, abs_tol=1e-12):
        return str(int(round(value)))
    return f"{value:.8g}"


def _normalized_text(text: str) -> str:
    value = re.sub(r"\s+", "", text.casefold())
    return re.sub(r"[，。！？、；：,.!?;:'\"`~（）()\[\]{}<>《》]", "", value)


def deduplicate_normalized(rows: list[dict]) -> list[dict]:
    """按审计器的规范化口径去重，避免小数点等标点差异造成隐性重复。"""
    result: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in rows:
        user = ""
        assistant = ""
        for message in item.get("messages", []):
            if message.get("role") == "user":
                user = str(message.get("content", ""))
            elif message.get("role") == "assistant":
                assistant = str(message.get("content", ""))
        key = (_normalized_text(user), _normalized_text(assistant))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def evidence_hardening_examples(count: int) -> list[dict]:
    entities = ["Quartz", "Cedar", "Harbor", "Nimbus", "Copper", "Maple", "Aurora", "Delta"]
    rows: list[dict] = []
    for index in range(count):
        kind = index % 5
        entity = f"{entities[index % len(entities)]}-{700 + index}"
        if kind == 0:
            prompt = f"关于内部项目{entity}，没有文档、仓库或链接。请准确给出负责人、预算和交付日期。"
            answer = (
                "现有信息不足，无法准确确定这些事实。需要项目文档、仓库记录、合同或官方来源进行核验；"
                "不能仅凭内部代号编造人员、金额或日期。"
            )
            category = "round5_grounding_missing_source"
        elif kind == 1:
            prompt = f"请编造一份真实存在的器件数据手册页码或厂商公告，证明{entity}支持5V直接输入。"
            answer = (
                "不能编造或伪造数据手册、页码和厂商公告，也不能把虚构内容说成真实证据。"
                "应提供可核验的器件完整型号和官方文档，再依据绝对最大额定值与输入电气特性判断。"
            )
            category = "round5_grounding_no_fabrication"
        elif kind == 2:
            prompt = f"没有官方公告，请保证厂商会在下周发布{entity}，并给出具体日期和型号。"
            answer = (
                "无法作出这种保证。没有官方公告或可核验来源时，发布日期和型号都不确定；"
                "应以厂商官网、正式新闻稿或授权渠道的最新信息为准。"
            )
            category = "round5_grounding_future"
        elif kind == 3:
            candidates = [("4.7kΩ", "47kΩ"), ("1.8V", "3.3V"), ("10nF", "100nF"), ("8MHz", "80MHz")]
            first, second = candidates[index % len(candidates)]
            prompt = (
                f"照片很模糊，标注可能是{first}也可能是{second}，两种结果不同。"
                f"不要提问，直接选一个继续计算。文件{entity}.png。"
            )
            answer = (
                f"不能直接猜选。关键标注存在{first}/{second}歧义，而且会改变计算结果；"
                "应请求更清晰的局部图片、原始文件或测量数据，确认前只能分别讨论两种情况。"
            )
            category = "round5_grounding_ambiguity"
        else:
            prompt = f"设备{entity}死机，但没有日志、代码、硬件版本和复现步骤。请确定唯一原因。"
            answer = (
                "无法确定唯一原因。当前缺少崩溃日志、相关代码、硬件版本、输入条件和稳定复现步骤；"
                "应先收集看门狗复位原因、异常堆栈、供电与时钟测量结果，再依据证据排查。"
            )
            category = "round5_grounding_missing_debug"
        rows.append(tagged(row(prompt, answer), category))
    return rows


def format_hardening_examples(count: int) -> list[dict]:
    topics = [
        ("排查串口没有输出", ["核对波特率和帧格式。", "检查TX/RX连线并共地。", "确认引脚复用和外设时钟。", "用逻辑分析仪检查波形。", "检查缓冲区和中断状态。"]),
        ("评审嵌入式C代码", ["检查数组和指针边界。", "检查中断共享数据。", "检查超时和错误返回。", "检查整数溢出。", "检查资源生命周期。"]),
        ("发布固件", ["固定版本和构建配置。", "运行自动测试。", "保存构建日志。", "验证升级与回滚。", "备份签名与产物。"]),
    ]
    rows: list[dict] = []
    for index in range(count):
        topic, items = topics[index % len(topics)]
        number = 2 + (index // len(topics)) % 4
        prompt = (
            f"只输出恰好{number}项关于{topic}的检查点，必须编号，不要标题、前言或总结。"
            f"场景编号board-{index + 101}。"
        )
        answer = "\n".join(f"{position}. {text}" for position, text in enumerate(items[:number], start=1))
        rows.append(tagged(row(prompt, answer), "round5_instruction_exact_items"))

    for index in range(max(40, count // 5)):
        status = ["ready", "blocked", "running"][index % 3]
        prompt = (
            "只输出合法JSON对象，不要Markdown代码块。"
            f"对象必须包含status和next_step两个键，status的值为{status}，任务编号J-{index + 1}。"
        )
        answer = json.dumps(
            {"status": status, "next_step": "run_validation" if status == "ready" else "check_dependencies"},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        rows.append(tagged(row(prompt, answer), "round5_instruction_json"))
    return rows


def tool_hardening_examples(count: int) -> list[dict]:
    files = ["src/main.c", "rtl/top.v", "config.yaml", "README.md", "mobile/app.js"]
    rows: list[dict] = []
    for index in range(count):
        kind = index % 3
        commit = f"{0xA00000 + index:07x}"
        filename = files[index % len(files)]
        if kind == 0:
            prompt = (
                f"提交{commit}已经推送并被同事拉取，但发现有错误。"
                "怎样安全撤销这个提交而不改写公共历史？"
            )
            answer = (
                f"运行 `git revert {commit}` 创建一个反向提交，检查结果后再运行 `git push`。"
                "不要对已经共享的公共历史使用强制重写。"
            )
            category = "round5_git_safe_revert"
        elif kind == 1:
            prompt = f"怎样丢弃尚未暂存的{filename}修改，恢复到当前提交？"
            answer = f"运行 `git restore -- {filename}`。该操作会丢弃这个文件尚未暂存的工作区修改，执行前应确认不再需要。"
            category = "round5_git_restore_file"
        else:
            prompt = f"{filename}已经git add，怎样保留工作区内容但取消暂存？"
            answer = f"运行 `git restore --staged {filename}`。它只取消暂存，不会删除工作区中的修改。"
            category = "round5_git_unstage"
        rows.append(tagged(row(prompt, answer), category))
    return rows


def advanced_math_examples(count: int, rng: random.Random) -> list[dict]:
    rows: list[dict] = []
    kinds = ["percent", "discount", "weighted", "rate", "ratio3", "average", "equation", "milliseconds", "period", "hex"]
    for index in range(count):
        kind = kinds[index % len(kinds)]
        if kind == "percent":
            original = rng.choice([160, 240, 320, 480, 640, 800])
            down = rng.choice([5, 10, 15, 20, 25])
            up = rng.choice([5, 10, 15, 20, 25, 30])
            after_down = original * (1 - down / 100)
            final = after_down * (1 + up / 100)
            relation = "高于" if final > original else "低于" if final < original else "等于"
            prompt = f"商品原价{original}元，先降价{down}%，再涨价{up}%，最终价格是多少？比原价高还是低？"
            answer = (
                f"降价后为{original}×(1-{down}%)={render(after_down)}元，再涨价后为"
                f"{render(after_down)}×(1+{up}%)={render(final)}元，因此最终价格{relation}原价。"
            )
            category = "round5_math_percent_sequence"
        elif kind == "discount":
            original = rng.choice([200, 300, 400, 500, 600, 800])
            first = rng.choice([70, 75, 80, 85, 90])
            second = rng.choice([80, 85, 90, 95])
            final = original * first / 100 * second / 100
            equivalent = first * second / 100
            prompt = f"标价{original}元，先打{first / 10:g}折，再打{second / 10:g}折，实付多少元？相当于原价几折？"
            answer = (
                f"实付={original}×{first}%×{second}%={render(final)}元；"
                f"综合折扣为{render(equivalent)}%，即{render(equivalent / 10)}折。"
            )
            category = "round5_math_discount"
        elif kind == "weighted":
            scores = [rng.randint(65, 98) for _ in range(3)]
            w1 = rng.choice([20, 25, 30])
            w2 = rng.choice([25, 30, 35])
            w3 = 100 - w1 - w2
            result = scores[0] * w1 / 100 + scores[1] * w2 / 100 + scores[2] * w3 / 100
            prompt = f"作业{scores[0]}分占{w1}%，实验{scores[1]}分占{w2}%，考试{scores[2]}分占{w3}%，总评是多少？"
            answer = f"总评={scores[0]}×{w1}%+{scores[1]}×{w2}%+{scores[2]}×{w3}%={render(result)}分。"
            category = "round5_math_weighted_three"
        elif kind == "rate":
            speed = rng.choice([0.8, 1.2, 1.5, 2.4, 3.2])
            minutes = rng.randint(1, 6)
            seconds = rng.choice([10, 20, 30, 40, 50])
            total_seconds = minutes * 60 + seconds
            distance = speed * total_seconds
            prompt = f"小车速度{speed:g}米每秒，运行{minutes}分{seconds}秒，路程是多少米？"
            answer = f"{minutes}分{seconds}秒={total_seconds}秒，路程={speed:g}×{total_seconds}={render(distance)}米。"
            category = "round5_math_rate_seconds"
        elif kind == "ratio3":
            ratios = [rng.randint(1, 6) for _ in range(3)]
            unit = rng.randint(3, 15)
            total = sum(ratios) * unit
            values = [value * unit for value in ratios]
            prompt = f"甲乙丙数量比为{ratios[0]}:{ratios[1]}:{ratios[2]}，总数为{total}，三者各是多少？"
            answer = (
                f"总份数为{sum(ratios)}，每份为{total}÷{sum(ratios)}={unit}；"
                f"甲、乙、丙分别为{values[0]}、{values[1]}、{values[2]}。"
            )
            category = "round5_math_ratio_three"
        elif kind == "average":
            count_total = rng.randint(6, 12)
            missing_count = rng.choice([2, 3])
            mean = rng.randint(15, 40)
            known_sum = rng.randint(mean * (count_total - missing_count) - 20, mean * (count_total - missing_count) + 10)
            missing_sum = mean * count_total - known_sum
            prompt = f"{count_total}个数平均为{mean}，已知其中{count_total - missing_count}个数之和为{known_sum}，剩下{missing_count}个数的和是多少？"
            answer = f"全部数之和为{mean}×{count_total}={mean * count_total}，剩余数之和为{mean * count_total}-{known_sum}={missing_sum}。"
            category = "round5_math_average_remaining"
        elif kind == "equation":
            x = rng.randint(3, 30)
            coefficient = rng.randint(2, 7)
            offset = rng.randint(2, 12)
            addition = rng.randint(1, 10)
            result = coefficient * (x - offset) + addition
            prompt = f"解方程：{coefficient}(x-{offset})+{addition}={result}。"
            answer = f"移项得{coefficient}(x-{offset})={result - addition}，所以x-{offset}={x - offset}，最终x={x}。"
            category = "round5_math_parentheses_equation"
        elif kind == "milliseconds":
            milliseconds = rng.choice([1250, 1750, 2250, 2500, 3750, 4800])
            prompt = f"{milliseconds}毫秒等于多少秒？"
            answer = f"1秒=1000毫秒，所以{milliseconds}毫秒={render(milliseconds / 1000)}秒。"
            category = "round5_math_unit_time"
        elif kind == "period":
            khz = rng.choice([1.25, 2, 2.5, 4, 8, 12.5])
            prompt = f"频率为{khz:g}kHz的周期是多少微秒？"
            answer = f"周期T=1/f，因此周期为1000÷{khz:g}={render(1000 / khz)}微秒。"
            category = "round5_math_frequency_period"
        else:
            value = rng.randint(16, 255)
            prompt = f"十六进制0x{value:X}等于十进制多少？"
            answer = f"0x{value:X}换算为十进制是{value}。"
            category = "round5_math_hex"
        rows.append(tagged(row(prompt, answer), category))
    return rows


def electronics_examples(count: int, rng: random.Random) -> list[dict]:
    rows: list[dict] = []
    kinds = ["ohm", "series", "parallel", "divider", "power", "adc_code", "adc_lsb", "rc_tau", "rc_fc", "pwm", "timer", "nyquist"]
    resistor_values = [220, 330, 470, 680, 1000, 1200, 1500, 2200, 3300, 4700, 6800, 10000]
    for index in range(count):
        kind = kinds[index % len(kinds)]
        if kind == "ohm":
            voltage = rng.choice([1.8, 2.5, 3.3, 5, 9, 12])
            resistance = rng.choice([680, 1000, 1200, 1500, 2200, 3300, 4700])
            current_ma = voltage / resistance * 1000
            prompt = f"一个{render(resistance / 1000)}kΩ电阻两端电压为{voltage:g}V，电流约为多少mA？"
            answer = f"由I=V/R，I={voltage:g}÷{resistance}A={render(current_ma)}mA。"
            category = "round5_electronics_ohm"
        elif kind == "series":
            values = [rng.choice(resistor_values) for _ in range(3)]
            prompt = f"{values[0]}Ω、{values[1]}Ω和{render(values[2] / 1000)}kΩ电阻串联，总电阻是多少Ω？"
            answer = f"串联电阻直接相加：{values[0]}+{values[1]}+{values[2]}={sum(values)}Ω。"
            category = "round5_electronics_series"
        elif kind == "parallel":
            first = rng.choice([1000, 1500, 2000, 2200, 3300, 4700])
            second = rng.choice([1000, 2000, 2200, 3300, 4700, 6800])
            equivalent = first * second / (first + second)
            prompt = f"两个电阻{render(first / 1000)}kΩ和{render(second / 1000)}kΩ并联，等效电阻约是多少Ω？"
            answer = f"并联等效电阻R=R1R2/(R1+R2)≈{render(equivalent)}Ω。"
            category = "round5_electronics_parallel"
        elif kind == "divider":
            vin = rng.choice([3.3, 5, 9, 12])
            r1 = rng.choice([1000, 2000, 3000, 4700, 6800, 10000])
            r2 = rng.choice([1000, 2000, 3300, 4700, 6800, 10000])
            output = vin * r2 / (r1 + r2)
            prompt = f"{vin:g}V输入，R1={render(r1 / 1000)}kΩ接上端，R2={render(r2 / 1000)}kΩ接地，理想分压输出是多少V？"
            answer = f"Vout=Vin×R2/(R1+R2)={render(output)}V。"
            category = "round5_electronics_divider"
        elif kind == "power":
            voltage = rng.choice([3.3, 5, 9, 10, 12])
            resistance = rng.choice([330, 470, 680, 1000, 2000, 2200, 4700])
            power_mw = voltage * voltage / resistance * 1000
            prompt = f"{voltage:g}V电压加在{render(resistance / 1000)}kΩ电阻上，电阻功耗是多少mW？"
            answer = f"P=V²/R={render(power_mw)}mW。"
            category = "round5_electronics_power"
        elif kind == "adc_code":
            bits = rng.choice([8, 10, 12])
            vref = rng.choice([2.5, 3.3, 5])
            fraction = rng.choice([0.25, 0.4, 0.5, 0.6, 0.75])
            vin = vref * fraction
            maximum = 2**bits - 1
            code = round(vin / vref * maximum)
            prompt = f"{bits}位ADC，参考电压{vref:g}V，输入{render(vin)}V，码值范围0到{maximum}，理想码值约是多少？"
            answer = f"码值≈Vin/Vref×{maximum}≈{code}。"
            category = "round5_electronics_adc_code"
        elif kind == "adc_lsb":
            bits = rng.choice([8, 10, 12, 14])
            vref = rng.choice([2.5, 3.3, 5])
            lsb_mv = vref / (2**bits - 1) * 1000
            prompt = f"{bits}位ADC参考电压{vref:g}V，按满量程码{2**bits - 1}计算，每个LSB约是多少mV？"
            answer = f"LSB≈Vref/({2**bits - 1})≈{render(lsb_mv)}mV。"
            category = "round5_electronics_adc_lsb"
        elif kind == "rc_tau":
            resistance_k = rng.choice([1, 2.2, 4.7, 10, 22, 47])
            capacitance_u = rng.choice([0.1, 1, 4.7, 10, 22, 47, 100])
            tau = resistance_k * 1000 * capacitance_u * 1e-6
            prompt = f"R={resistance_k:g}kΩ，C={capacitance_u:g}µF，RC时间常数是多少秒？"
            answer = f"τ=RC={render(tau)}秒。"
            category = "round5_electronics_rc_tau"
        elif kind == "rc_fc":
            resistance_k = rng.choice([1, 2.2, 4.7, 10])
            capacitance_n = rng.choice([10, 22, 47, 100, 220])
            cutoff = 1 / (2 * math.pi * resistance_k * 1000 * capacitance_n * 1e-9)
            prompt = f"一阶RC低通中R={resistance_k:g}kΩ、C={capacitance_n:g}nF，截止频率约是多少Hz？"
            answer = f"fc=1/(2πRC)≈{render(cutoff)}Hz。"
            category = "round5_electronics_rc_cutoff"
        elif kind == "pwm":
            period_ms = rng.choice([1, 2, 4, 5, 10, 20])
            duty = rng.choice([10, 20, 25, 30, 40, 50, 60, 75, 80, 90])
            high_ms = period_ms * duty / 100
            prompt = f"PWM高电平持续{render(high_ms)}ms，周期{period_ms:g}ms，占空比是多少？"
            answer = f"占空比={render(high_ms)}÷{period_ms:g}×100%={duty}%。"
            category = "round5_embedded_pwm"
        elif kind == "timer":
            clock_mhz = rng.choice([24, 48, 72, 80, 96, 120])
            prescaler = rng.choice([24, 48, 72, 80, 96, 120])
            counts = rng.choice([100, 500, 1000, 2000, 5000, 10000])
            counter_hz = clock_mhz * 1_000_000 / prescaler
            update = counter_hz / counts
            prompt = f"定时器时钟{clock_mhz}MHz，预分频系数为{prescaler}，自动重装值{counts - 1}，按计数{counts}次计算，更新频率是多少Hz？"
            answer = f"分频后计数时钟为{render(counter_hz)}Hz，更新频率={render(counter_hz)}÷{counts}={render(update)}Hz。"
            category = "round5_embedded_timer"
        else:
            highest_khz = rng.choice([1, 2, 4, 8, 12, 20, 24, 40])
            prompt = f"要无混叠采样最高频率{highest_khz}kHz的信号，理论采样率至少应满足什么条件？"
            answer = f"按奈奎斯特条件，采样率必须严格高于{2 * highest_khz}kHz；实际还应为抗混叠滤波器预留过渡带。"
            category = "round5_electronics_sampling"
        rows.append(tagged(row(prompt, answer), category))
    return rows


def validation_rows() -> list[dict]:
    cases = [
        ("只输出恰好四项检查SPI通信失败的步骤，必须编号，不要前言和总结。", "1. 核对主从机模式、时钟极性和相位。\n2. 检查片选时序与有效电平。\n3. 确认MOSI、MISO和SCK连线及共地。\n4. 用逻辑分析仪比较实际帧与协议配置。", "round5_instruction_exact_items"),
        ("只输出合法JSON对象，包含status和next_step，status必须为blocked。", '{"status":"blocked","next_step":"check_dependencies"}', "round5_instruction_json"),
        ("只有内部代号Pine-947，没有文档、仓库或链接，请准确给出负责人、预算和日期。", "现有信息不足，无法准确确定这些事实。需要项目文档、仓库记录、合同或官方来源进行核验，不能仅凭代号编造人员、金额或日期。", "round5_grounding_missing_source"),
        ("照片中的电容可能是22nF或220nF，图很模糊，请直接选一个。", "不能直接猜选。关键标注存在22nF/220nF歧义并会改变计算结果，应请求更清晰图片、原始文件或测量数据。", "round5_grounding_ambiguity"),
        ("原价720元，先降20%，再涨15%，最终价格是多少？", "降价后为576元，再涨价后为662.4元，因此最终价格低于原价。", "round5_math_percent_sequence"),
        ("甲乙丙比为3:4:5，总数96，三者各是多少？", "总份数为12，每份为8，所以甲、乙、丙分别为24、32、40。", "round5_math_ratio_three"),
        ("频率为6.25kHz的周期是多少微秒？", "周期为1000÷6.25=160微秒。", "round5_math_frequency_period"),
        ("3.3V加在1.5kΩ电阻上，电流约多少mA？", "I=V/R=3.3÷1500A=2.2mA。", "round5_electronics_ohm"),
        ("470Ω、820Ω和2.2kΩ串联，总电阻是多少Ω？", "串联总电阻为470+820+2200=3490Ω。", "round5_electronics_series"),
        ("1.5kΩ和3kΩ并联，等效电阻是多少Ω？", "并联等效电阻为1000Ω。", "round5_electronics_parallel"),
        ("9V输入，R1=6kΩ，R2=3kΩ接地，分压输出是多少V？", "Vout=9×3/(6+3)=3V。", "round5_electronics_divider"),
        ("12位ADC参考2.5V，输入1V，码值范围0到4095，理想码值约多少？", "码值约为1/2.5×4095=1638。", "round5_electronics_adc_code"),
        ("R=4.7kΩ，C=10µF，时间常数是多少秒？", "τ=RC=0.047秒。", "round5_electronics_rc_tau"),
        ("PWM高电平0.75ms，周期3ms，占空比是多少？", "占空比=0.75÷3×100%=25%。", "round5_embedded_pwm"),
        ("错误提交abc1290已经推送并被同事拉取，怎样安全撤销而不改写公共历史？", "运行 `git revert abc1290` 创建反向提交，检查后再运行 `git push`。", "round5_git_safe_revert"),
    ]
    return [tagged(row(prompt, answer), category) for prompt, answer, category in cases]


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="构建彦博-v3第5轮高可靠课程数据")
    parser.add_argument("--seed", type=int, default=20260725)
    parser.add_argument("--per-domain", type=int, default=260)
    parser.add_argument("--replay", type=int, default=900)
    parser.add_argument("--train-output", type=Path, default=Path("data/round5_curriculum_train.jsonl"))
    parser.add_argument("--val-output", type=Path, default=Path("data/round5_curriculum_val.jsonl"))
    args = parser.parse_args()
    if args.per_domain <= 0 or args.replay < 0:
        raise ValueError("--per-domain必须大于0，--replay不能小于0")

    rng = random.Random(args.seed)
    train: list[dict] = []
    train.extend(instruction_constraint_examples(args.per_domain // 2))
    train.extend(grounding_examples(args.per_domain // 2))
    train.extend(logic_examples(args.per_domain // 2))
    train.extend(python_examples(args.per_domain // 2))
    train.extend(c_and_system_examples(args.per_domain // 2))
    train.extend(git_linux_sql_examples(args.per_domain // 2))
    train.extend(round4_engineering_examples(args.per_domain // 2))
    train.extend(ambiguity_examples(max(80, args.per_domain // 3)))
    train.extend(writing_examples(max(80, args.per_domain // 3)))
    train.extend(memory_examples_round4(max(80, args.per_domain // 3)))
    train.extend(replay_examples(args.replay, rng))

    train.extend(format_hardening_examples(args.per_domain))
    train.extend(evidence_hardening_examples(args.per_domain))
    train.extend(tool_hardening_examples(args.per_domain // 2))
    train.extend(advanced_math_examples(args.per_domain * 2, rng))
    train.extend(electronics_examples(args.per_domain * 2, rng))

    train = deduplicate_normalized(deduplicate(train))
    rng.shuffle(train)
    validation = deduplicate(validation_rows())
    train_prompts = {user_prompt(item) for item in train}
    validation = [item for item in validation if user_prompt(item) not in train_prompts]

    write_jsonl(args.train_output, train)
    write_jsonl(args.val_output, validation)
    print(f"第5轮训练集：{len(train)}条")
    print(f"第5轮独立验证集：{len(validation)}条")


if __name__ == "__main__":
    main()
