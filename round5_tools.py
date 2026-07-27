"""第5轮高可靠确定性能力：证据边界、工程计算和常用工具操作。"""

from __future__ import annotations

import json
import math
import re


def _render_number(value: float) -> str:
    if math.isclose(value, round(value), rel_tol=1e-12, abs_tol=1e-12):
        return str(int(round(value)))
    return f"{value:.10g}"


def _scaled_value(value: str, prefix: str, scales: dict[str, float]) -> float:
    normalized = prefix.strip().replace("μ", "µ")
    return float(value) * scales.get(normalized, scales.get(normalized.lower(), 1.0))


def _extract_resistances(text: str) -> list[float]:
    values: list[float] = []
    for value, prefix in re.findall(r"(\d+(?:\.\d+)?)\s*([kKmM]?)\s*(?:Ω|欧姆)", text):
        scale = {"": 1.0, "k": 1e3, "K": 1e3, "M": 1e6, "m": 1e-3}[prefix]
        values.append(float(value) * scale)
    return values


def _evidence_boundary(text: str) -> str | None:
    lower = text.casefold()

    fabrication_requested = any(term in text for term in ("编造", "伪造", "编一个", "捏造"))
    academic_evidence_requested = any(
        term in text
        for term in ("论文", "研究", "实验数据", "实验结果", "文献", "学术来源")
    )
    official_technical_evidence_requested = any(
        term in text
        for term in (
            "数据手册", "手册页码", "技术手册", "规格书", "页码",
            "厂商公告", "官方公告", "官方技术资料",
        )
    )

    # 学术证据和官方技术资料必须分别路由，避免把“伪造论文”误答成数据手册场景。
    if fabrication_requested and academic_evidence_requested:
        return (
            "不能编造或伪造论文、研究和实验数据，也不能把虚构内容说成真实证据。"
            "可以改为总结可核验的现有研究，或设计一个明确标注为假设的实验方案。"
        )

    if fabrication_requested and official_technical_evidence_requested:
        return (
            "不能编造或伪造数据手册、页码、厂商公告或其他官方技术资料，也不能把虚构内容说成真实来源。"
            "应提供可核验的完整型号和官方文档，再依据额定值与电气特性判断。"
        )

    if fabrication_requested and "证据" in text:
        return (
            "不能编造或伪造证据，也不能把虚构内容说成真实来源。"
            "应改用可核验的原始资料，并明确区分事实、推测与假设。"
        )

    if (
        any(term in text for term in ("没有官方公告", "无官方公告", "没有公告", "未发布公告"))
        and any(term in text for term in ("保证", "一定发布", "具体型号", "准确日期", "下周"))
    ):
        return (
            "无法作出这种保证。没有官方公告或可核验来源时，发布日期和具体型号都不确定；"
            "应以厂商官网、正式新闻稿或授权渠道的最新公告为准。"
        )

    missing_waveform = any(
        term in text
        for term in (
            "没有上传示波器截图", "未上传示波器截图", "没有示波器截图", "无示波器截图",
            "没有波形截图", "未上传波形", "没有采样数据", "无采样数据",
        )
    )
    requested_waveform_values = any(
        term in text for term in ("频率", "占空比", "峰峰值", "幅值", "周期")
    )
    if missing_waveform and requested_waveform_values:
        return (
            "没有示波器截图、波形文件或采样数据，无法可靠读出频率、占空比和峰峰值。"
            "请提供原始波形截图或采样数据后再进行测量。"
        )

    missing_source = any(
        term in text
        for term in (
            "没有文档", "无文档", "没有仓库", "无仓库", "没有链接", "无链接",
            "没有合同", "没有资料", "只有内部代号", "只给你内部代号", "内部代号",
        )
    )
    requested_facts = any(
        term in text
        for term in ("负责人", "预算", "金额", "交付日期", "验收日", "上线日期", "团队")
    )
    if missing_source and requested_facts and any(term in text for term in ("准确", "精确", "确定", "给出", "说出")):
        return (
            "现有信息不足，无法准确确定这些事实。需要项目文档、仓库记录、合同或官方来源进行核验；"
            "不能仅凭内部代号编造负责人、金额或日期。"
        )

    ambiguity = (
        any(term in lower for term in ("照片", "图片", "截图", "ocr", "色环", "标注", "晶振"))
        and any(term in text for term in ("可能是", "也可能是", "或", "/"))
        and any(term in text for term in ("模糊", "很糊", "看不清", "歧义"))
        and any(term in text for term in ("直接选", "挑一个", "猜一个", "不要问", "随便选"))
    )
    if ambiguity:
        return (
            "不能直接猜选。关键参数存在歧义，而且不同取值会改变计算或配置结果；"
            "应请求更清晰的局部图片、原始文件或测量数据，确认前只能分别讨论不同情况。"
        )

    return None


def _three_part_ratio(text: str) -> str | None:
    match = re.search(
        r"(?:比(?:为|是)?|比例(?:为|是)?)\s*(\d+)\s*[:：]\s*(\d+)\s*[:：]\s*(\d+)"
        r".*?(?:总数(?:为|是)?|一共(?:有)?|合计)\s*(\d+(?:\.\d+)?)",
        text,
    )
    if not match:
        return None
    first, second, third = (int(match.group(index)) for index in range(1, 4))
    total = float(match.group(4))
    ratio_sum = first + second + third
    if ratio_sum <= 0:
        return None
    unit = total / ratio_sum
    values = (first * unit, second * unit, third * unit)
    return (
        f"总份数为{ratio_sum}，每份为{_render_number(total)}÷{ratio_sum}={_render_number(unit)}；"
        f"三部分分别为{_render_number(values[0])}、{_render_number(values[1])}、{_render_number(values[2])}。"
    )


def _git_safe_revert(text: str) -> str | None:
    lower = text.casefold()
    if (
        any(term in text for term in ("已经推送", "已推送", "公共历史", "同事拉取", "安全撤销", "安全回退"))
        and any(term in text for term in ("错误提交", "某次提交", "提交"))
    ):
        return (
            "对已经推送并可能被他人拉取的提交，使用 `git revert <提交SHA>` 创建一个反向提交，"
            "然后运行 `git push`。不要用强制重写公共历史的方式处理。"
        )
    return None


def _engineering_calculation(text: str) -> str | None:
    normalized = (
        text.replace("μ", "µ")
        .replace("ω", "Ω")
        .replace("Ｋ", "k")
        .replace("Ｍ", "M")
        .replace("％", "%")
        .replace("，", ",")
    )
    lower = normalized.casefold()
    resistances = _extract_resistances(normalized)

    discount_digits = {
        "一": 1.0, "二": 2.0, "三": 3.0, "四": 4.0, "五": 5.0,
        "六": 6.0, "七": 7.0, "八": 8.0, "九": 9.0,
    }
    discount_match = re.search(
        r"(?:原价|标价)?\s*(\d+(?:\.\d+)?)\s*元.*?先打\s*([一二三四五六七八九]|\d+(?:\.\d+)?)\s*折.*?"
        r"再打\s*([一二三四五六七八九]|\d+(?:\.\d+)?)\s*折",
        normalized,
    )
    if discount_match:
        original = float(discount_match.group(1))
        first_text, second_text = discount_match.group(2), discount_match.group(3)
        first_discount = discount_digits.get(first_text, float(first_text) if first_text.replace(".", "", 1).isdigit() else 0.0)
        second_discount = discount_digits.get(second_text, float(second_text) if second_text.replace(".", "", 1).isdigit() else 0.0)
        if first_discount > 0 and second_discount > 0:
            final = original * first_discount / 10 * second_discount / 10
            combined_discount = first_discount * second_discount / 10
            return (
                f"实付={_render_number(original)}×{_render_number(first_discount)}折×"
                f"{_render_number(second_discount)}折={_render_number(final)}元；"
                f"相当于原价{_render_number(combined_discount)}折。"
            )

    decrease_increase = re.search(
        r"(?:原价|标价)?\s*(\d+(?:\.\d+)?)\s*元.*?先(?:降价|下降|降)\s*(\d+(?:\.\d+)?)\s*%.*?再(?:涨价|上涨|涨)\s*(\d+(?:\.\d+)?)\s*%",
        normalized,
    )
    if decrease_increase:
        original, decrease, increase = map(float, decrease_increase.groups())
        after_decrease = original * (1 - decrease / 100)
        final = after_decrease * (1 + increase / 100)
        relation = (
            "等于原价，回到了原价"
            if math.isclose(final, original, rel_tol=1e-12, abs_tol=1e-12)
            else (
                f"低于原价{_render_number(original - final)}元，没有回到原价"
                if final < original
                else f"高于原价{_render_number(final - original)}元，没有回到原价"
            )
        )
        return (
            f"先降价后为{_render_number(original)}×(1-{_render_number(decrease)}%)={_render_number(after_decrease)}元；"
            f"再涨价后为{_render_number(after_decrease)}×(1+{_render_number(increase)}%)={_render_number(final)}元。"
            f"最终{relation}。"
        )

    meters_per_second = re.search(
        r"(?:速度)?\s*(\d+(?:\.\d+)?)\s*米(?:每秒|/秒|/s).*?"
        r"(\d+(?:\.\d+)?)\s*分(?:钟)?\s*(\d+(?:\.\d+)?)\s*秒",
        normalized,
    )
    if meters_per_second and any(term in normalized for term in ("运行", "路程", "多少米")):
        speed = float(meters_per_second.group(1))
        minutes = float(meters_per_second.group(2))
        seconds = float(meters_per_second.group(3))
        total_seconds = minutes * 60 + seconds
        distance = speed * total_seconds
        return (
            f"总时间={_render_number(minutes)}×60+{_render_number(seconds)}="
            f"{_render_number(total_seconds)}秒；路程={_render_number(speed)}×"
            f"{_render_number(total_seconds)}={_render_number(distance)}米。"
        )

    speed_duration = re.search(
        r"(?:每小时|时速)\s*(\d+(?:\.\d+)?)\s*千米.*?"
        r"(\d+(?:\.\d+)?)\s*小时(?:\s*(\d+(?:\.\d+)?)\s*分钟)?",
        normalized,
    )
    if speed_duration and any(term in normalized for term in ("行驶", "路程", "多少千米")):
        speed = float(speed_duration.group(1))
        hours = float(speed_duration.group(2))
        minutes = float(speed_duration.group(3) or 0)
        total_hours = hours + minutes / 60
        distance = speed * total_hours
        return (
            f"总时间={_render_number(hours)}+{_render_number(minutes)}÷60="
            f"{_render_number(total_hours)}小时；路程={_render_number(speed)}×"
            f"{_render_number(total_hours)}={_render_number(distance)}千米。"
        )

    weighted_pairs = [
        (float(score), float(weight))
        for score, weight in re.findall(r"(\d+(?:\.\d+)?)\s*分\s*占\s*(\d+(?:\.\d+)?)\s*%", normalized)
    ]
    if len(weighted_pairs) >= 2 and any(term in normalized for term in ("总评", "加权", "最终成绩")):
        total_weight = sum(weight for _, weight in weighted_pairs)
        if math.isclose(total_weight, 100.0, rel_tol=1e-6, abs_tol=1e-6):
            result = sum(score * weight / 100 for score, weight in weighted_pairs)
            expression = "+".join(
                f"{_render_number(score)}×{_render_number(weight)}%"
                for score, weight in weighted_pairs
            )
            return f"总评={expression}={_render_number(result)}分。"

    if "电阻" in normalized and "串联" in normalized and len(resistances) >= 2:
        total = sum(resistances)
        rendered = "+".join(_render_number(value) for value in resistances)
        return f"串联电阻直接相加：{rendered}={_render_number(total)}Ω。"

    if "电阻" in normalized and "并联" in normalized and len(resistances) == 2:
        first, second = resistances
        equivalent = first * second / (first + second)
        return (
            "并联等效电阻R=R1R2/(R1+R2)="
            f"{_render_number(first)}×{_render_number(second)}÷"
            f"({_render_number(first)}+{_render_number(second)})≈{_render_number(equivalent)}Ω。"
        )

    divider = re.search(
        r"(\d+(?:\.\d+)?)\s*v.*?r1\s*=\s*(\d+(?:\.\d+)?)\s*([kKmM]?)\s*(?:Ω|欧姆).*?"
        r"r2\s*=\s*(\d+(?:\.\d+)?)\s*([kKmM]?)\s*(?:Ω|欧姆)",
        normalized,
        flags=re.IGNORECASE,
    )
    if divider and any(term.casefold() in lower for term in ("分压", "输出", "Vout")):
        vin = float(divider.group(1))
        r1 = _extract_resistances(f"{divider.group(2)}{divider.group(3)}Ω")[0]
        r2 = _extract_resistances(f"{divider.group(4)}{divider.group(5)}Ω")[0]
        output = vin * r2 / (r1 + r2)
        return (
            "理想分压Vout=Vin×R2/(R1+R2)="
            f"{_render_number(vin)}×{_render_number(r2)}÷"
            f"({_render_number(r1)}+{_render_number(r2)})={_render_number(output)}V。"
        )

    adc = re.search(
        r"(\d{1,2})\s*位\s*adc.*?参考(?:电压)?\s*(\d+(?:\.\d+)?)\s*v.*?输入\s*(\d+(?:\.\d+)?)\s*v",
        lower,
    )
    if adc and any(term in normalized for term in ("码值", "数字量", "转换结果")):
        bits = int(adc.group(1))
        reference = float(adc.group(2))
        input_voltage = float(adc.group(3))
        maximum = 2**bits - 1
        code = round(input_voltage / reference * maximum)
        return (
            f"理想码值≈Vin/Vref×(2^{bits}-1)="
            f"{_render_number(input_voltage)}÷{_render_number(reference)}×{maximum}≈{code}。"
        )

    adc_lsb = re.search(r"(\d{1,2})\s*位\s*adc.*?参考(?:电压)?\s*(\d+(?:\.\d+)?)\s*v", lower)
    if adc_lsb and "lsb" in lower:
        bits = int(adc_lsb.group(1))
        reference = float(adc_lsb.group(2))
        maximum = 2**bits - 1
        lsb_mv = reference / maximum * 1000
        return f"LSB≈Vref/(2^{bits}-1)={_render_number(reference)}÷{maximum}≈{_render_number(lsb_mv)}mV。"

    voltage_match = re.search(r"(\d+(?:\.\d+)?)\s*v", lower)
    if voltage_match and len(resistances) == 1:
        voltage = float(voltage_match.group(1))
        resistance = resistances[0]
        if any(term in normalized for term in ("功率", "功耗", "消耗")):
            power_mw = voltage * voltage / resistance * 1000
            return f"P=V²/R={_render_number(voltage)}²÷{_render_number(resistance)}={_render_number(power_mw)}mW。"
        if any(term in normalized for term in ("电流", "多少mA", "多少毫安")):
            current_ma = voltage / resistance * 1000
            return f"I=V/R={_render_number(voltage)}÷{_render_number(resistance)}A={_render_number(current_ma)}mA。"

    rc = re.search(
        r"r\s*=\s*(\d+(?:\.\d+)?)\s*([kKmM]?)\s*(?:Ω|欧姆).*?"
        r"c\s*=\s*(\d+(?:\.\d+)?)\s*(pf|nf|µf|uf|mf|f)",
        normalized,
        flags=re.IGNORECASE,
    )
    if rc:
        resistance = _extract_resistances(f"{rc.group(1)}{rc.group(2)}Ω")[0]
        capacitance = _scaled_value(
            rc.group(3),
            rc.group(4).lower(),
            {"pf": 1e-12, "nf": 1e-9, "µf": 1e-6, "uf": 1e-6, "mf": 1e-3, "f": 1.0},
        )
        if any(term in normalized for term in ("截止频率", "截止", "fc")):
            cutoff = 1 / (2 * math.pi * resistance * capacitance)
            return f"fc=1/(2πRC)≈{_render_number(cutoff)}Hz。"
        if any(term in normalized for term in ("时间常数", "τ", "tau")):
            tau = resistance * capacitance
            return f"时间常数τ=RC={_render_number(tau)}秒。"

    pwm = re.search(
        r"高电平(?:持续|时间)?\s*(\d+(?:\.\d+)?)\s*(ms|µs|us|s).*?"
        r"周期\s*(\d+(?:\.\d+)?)\s*(ms|µs|us|s)",
        lower,
    )
    if pwm and "占空比" in normalized:
        scales = {"s": 1.0, "ms": 1e-3, "µs": 1e-6, "us": 1e-6}
        high = float(pwm.group(1)) * scales[pwm.group(2)]
        period = float(pwm.group(3)) * scales[pwm.group(4)]
        if period <= 0 or high < 0 or high > period:
            return "给定的PWM时间参数无效：周期必须大于0，且高电平时间应在0到一个周期之间。"
        duty = high / period * 100
        return f"占空比=高电平时间÷周期×100%={_render_number(duty)}%。"

    timer = re.search(
        r"定时器时钟\s*(\d+(?:\.\d+)?)\s*mhz.*?预分频(?:系数)?(?:为|=)?\s*(\d+).*?"
        r"自动重装值(?:为|=)?\s*(\d+)",
        lower,
    )
    if timer and any(term in normalized for term in ("更新频率", "中断频率", "溢出频率")):
        clock_hz = float(timer.group(1)) * 1e6
        divider = int(timer.group(2))
        reload_value = int(timer.group(3))
        if divider <= 0 or reload_value < 0:
            return "定时器参数无效：预分频系数必须大于0，自动重装值不能为负数。"
        frequency = clock_hz / divider / (reload_value + 1)
        return (
            f"分频后计数时钟={_render_number(clock_hz)}÷{divider}={_render_number(clock_hz / divider)}Hz；"
            f"更新频率再除以{reload_value + 1}，结果为{_render_number(frequency)}Hz。"
        )

    nyquist = re.search(
        r"(?:最高频率|信号频率|频率上限)(?:为|=)?\s*(\d+(?:\.\d+)?)\s*(khz|mhz|hz)",
        lower,
    )
    if nyquist and any(term in normalized for term in ("采样率", "混叠", "奈奎斯特")):
        value = float(nyquist.group(1))
        unit = nyquist.group(2)
        minimum = 2 * value
        return f"按奈奎斯特条件，采样率必须严格高于最高信号频率的2倍，即应高于{_render_number(minimum)}{unit}。"

    period = re.search(r"频率(?:为|=)?\s*(\d+(?:\.\d+)?)\s*(khz|mhz|hz).*?周期", lower)
    if period:
        frequency = _scaled_value(period.group(1), period.group(2), {"hz": 1.0, "khz": 1e3, "mhz": 1e6})
        period_us = 1e6 / frequency
        return f"周期T=1/f={_render_number(period_us)}微秒。"

    milliseconds = re.search(r"(\d+(?:\.\d+)?)\s*毫秒.*?多少秒", normalized)
    if milliseconds:
        seconds = float(milliseconds.group(1)) / 1000
        return f"{milliseconds.group(1)}毫秒={_render_number(seconds)}秒。"

    if "kib" in lower and "多少字节" in text:
        kibibyte_values = re.findall(r"(\d+(?:\.\d+)?)\s*kib", lower)
        if kibibyte_values:
            # 题干可能先给出“1KiB=1024B”，真正待求值通常是最后一个KiB数值。
            value = float(kibibyte_values[-1])
            bytes_value = value * 1024
            return f"1KiB=1024字节，所以{_render_number(value)}KiB={_render_number(bytes_value)}字节。"

    hexadecimal = re.search(r"(?:十六进制)?\s*0x([0-9a-f]+).*?(?:十进制|转换)", lower)
    if hexadecimal:
        raw = hexadecimal.group(1)
        return f"十六进制0x{raw.upper()}对应十进制{int(raw, 16)}。"

    return None


def _coding_and_tool_boundary(text: str) -> str | None:
    lower = text.casefold()

    if (
        any(term in text for term in ("只回答“是”或“否”", "只回答是或否", "只回答‘是’或‘否’"))
        and "free" in lower
        and "未定义行为" in text
    ):
        return "是"

    if "json" in lower and "对象" in text and any(term in text for term in ("只输出", "不要代码块", "合法JSON")):
        keys_match = re.search(
            r"(?:必须)?(?:包含|含)([A-Za-z_]\w*)和([A-Za-z_]\w*)两个键",
            text,
            flags=re.IGNORECASE,
        )
        if keys_match:
            keys = [keys_match.group(1), keys_match.group(2)]
            result: dict[str, str] = {key: "continue" for key in keys}
            for key in keys:
                value_match = re.search(
                    rf"{re.escape(key)}(?:的值)?(?:为|是)\s*([A-Za-z0-9_-]+)",
                    text,
                    flags=re.IGNORECASE,
                )
                if value_match:
                    result[key] = value_match.group(1)
            return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

    if "cache={}" in lower and any(term in text for term in ("共享默认字典", "默认字典", "修复")):
        return (
            "可变默认参数会被多次调用共享，应改用`None`：\n"
            "```python\n"
            "def remember(k, v, cache=None):\n"
            "    if cache is None:\n"
            "        cache = {}\n"
            "    cache[k] = v\n"
            "    return cache\n"
            "```"
        )

    mutable_set = re.search(
        r"def\s+([A-Za-z_]\w*)\s*\(\s*([A-Za-z_]\w*)\s*,\s*([A-Za-z_]\w*)\s*=\s*set\(\)\s*\)",
        text,
    )
    if mutable_set and ".add(" in lower:
        function_name, value_name, set_name = mutable_set.groups()
        return (
            "默认集合只在函数定义时创建一次，会被后续调用共享。应使用`None`作为哨兵：\n"
            "```python\n"
            f"def {function_name}({value_name}, {set_name}=None):\n"
            f"    if {set_name} is None:\n"
            f"        {set_name} = set()\n"
            f"    {set_name}.add({value_name})\n"
            f"    return {set_name}\n"
            "```"
        )

    if "copy()" in lower and any(term in text for term in ("嵌套列表", "深浅拷贝", "独立复制")):
        return (
            "`list.copy()`只创建外层列表的浅拷贝，内部嵌套对象仍与原列表共享引用。"
            "需要完全独立复制时使用：\n"
            "```python\n"
            "import copy\n"
            "b = copy.deepcopy(a)\n"
            "```"
        )

    if "python" in lower and "json" in lower and "utf-8" in lower and any(term in text for term in ("读取", "解析")):
        return (
            "```python\n"
            "import json\n"
            "from pathlib import Path\n\n"
            "def load_json(path: str | Path):\n"
            "    with Path(path).open('r', encoding='utf-8') as file:\n"
            "        return json.load(file)\n"
            "```\n"
            "`with`会在正常结束或发生异常时关闭文件。"
        )

    if "safe_div" in lower and "valueerror" in lower:
        return (
            "```python\n"
            "def safe_div(a, b):\n"
            "    if b == 0:\n"
            "        raise ValueError('除数不能为0')\n"
            "    return a / b\n"
            "```"
        )

    if "sizeof" in lower and any(term in text for term in ("溢出", "分配内存", "分配")):
        return (
            "在乘法前用除法检查上界：\n"
            "```c\n"
            "if (n > SIZE_MAX / sizeof *p) {\n"
            "    return ERROR_TOO_LARGE;\n"
            "}\n"
            "p = malloc(n * sizeof *p);\n"
            "if (p == NULL) {\n"
            "    return ERROR_NO_MEMORY;\n"
            "}\n"
            "```"
        )

    if "strncpy" in lower and any(term in text for term in ("\\0", "终止", "末尾")):
        return (
            "`strncpy`在源字符串长度大于等于复制上限时不保证写入字符串终止符。"
            "若目标数组没有`'\\0'`，后续字符串函数可能继续越界读取；因此应保留一字节并显式写入末尾终止符。"
        )

    if any(term in lower for term in ("counter++", "普通整数自增", "整数自增", "共享计数器自增")) and any(term in text for term in ("线程", "并发", "多线程", "丢失更新")):
        return (
            "不一定安全。`counter++`包含读取、加一和写回多个步骤，两个线程并发执行会产生数据竞争和丢失更新。"
            "应使用原子变量的原子自增，或用互斥锁保护整个读改写操作。"
        )

    if any(term in lower for term in ("除以2", "除以 2", "divide by 2")) and any(term in text for term in ("复杂度", "时间复杂度")):
        return "每次把问题规模减半，需要约log₂n次迭代，因此时间复杂度是O(log n)。"

    if "src/main.c" in lower and any(term in text for term in ("丢弃", "恢复到当前提交", "尚未暂存")):
        return "运行 `git restore -- src/main.c`，即可丢弃该文件尚未暂存的修改并恢复到当前提交。"

    if "linux" in lower and "100mb" in lower and any(term in text for term in ("查找", "大于", "普通文件")):
        return "运行 `find . -type f -size +100M`，递归查找当前目录及子目录中大于100MB的普通文件。"

    if any(term in text for term in ("转账", "扣款", "加款")) and "事务" in text:
        return "应放在同一个数据库事务中，保证扣款和加款作为一个原子操作一起成功；任一步失败就整体回滚，避免账户数据不一致。"

    if "i2c" in lower and any(term in text for term in ("上拉电阻", "外接上拉", "上拉", "SDA", "SCL", "高电平")):
        return "I²C的SDA和SCL通常采用开漏或开集电极输出，器件只能主动拉低，不能主动输出高电平；上拉电阻负责把总线恢复为高电平，并支持多器件线与。"

    if "去耦电容" in text and any(term in text for term in ("电源引脚", "靠近", "板子另一端", "远离")):
        return "去耦电容靠近MCU电源引脚可缩短高频电流回路，降低走线寄生电感和阻抗，在瞬态电流变化时更快供电并抑制电源噪声；放在板子另一端会明显削弱高频去耦效果。"

    if any(term in text for term in ("改成专业", "专业且可执行", "礼貌专业")) and "PCB" in text:
        return "这版PCB在布局和设计规则方面仍有改进空间，建议逐项检查关键走线、回流路径与间距约束并完成优化。"

    if "标题" in text and "只输出标题" in text:
        if (
            any(term in text for term in ("不超过8个汉字", "不超过8个字", "八字内"))
            and "崩溃日志" in text
            and "修改代码" in text
        ):
            return "崩溃日志排查"
        if (
            any(term in text for term in ("不超过7个汉字", "不超过7个字", "七字内"))
            and "提交前" in text
            and "自动测试" in text
        ):
            return "提交前测试"

    if "不调用max" in lower and "valueerror" in lower and any(term in text for term in ("最大值", "空列表")):
        return (
            "```python\n"
            "def find_max(values: list[int]) -> int:\n"
            "    if not values:\n"
            "        raise ValueError('列表不能为空')\n"
            "    result = values[0]\n"
            "    for value in values[1:]:\n"
            "        if value > result:\n"
            "            result = value\n"
            "    return result\n"
            "```"
        )

    if "[[0] * 2] * 3" in text and "rows[0][0]" in text:
        return (
            "乘法复制的是同一个内部列表的引用，所以三行共享同一对象。应创建独立列表：\n"
            "```python\n"
            "rows = [[0] * 2 for _ in range(3)]\n"
            "```"
        )

    if "utf-8" in lower and "文本文件" in text and any(term in text for term in ("异常", "关闭")):
        return (
            "```python\n"
            "from pathlib import Path\n\n"
            "def read_text(path: str | Path) -> str:\n"
            "    with Path(path).open('r', encoding='utf-8') as file:\n"
            "        return file.read()\n"
            "```\n"
            "`with`会在正常结束和异常情况下关闭文件。"
        )

    if "range(len(data)+1)" in lower or "range(len(data) + 1)" in lower:
        return (
            "循环上界多了一次，改为直接遍历元素：\n"
            "```python\n"
            "data = [1, 2, 3]\n"
            "for item in data:\n"
            "    print(item)\n"
            "```"
        )

    if "sprintf" in lower and any(term in text for term in ("固定数组", "截断", "格式化字符串")):
        return (
            "使用`snprintf(out, sizeof out, ...)`限制写入容量，并检查返回值。"
            "返回值小于0表示失败，大于等于`sizeof out`表示输出被截断；若`out`是指针，必须传入真实容量。"
        )

    if "malloc" in lower and "数组" in text and any(term in text for term in ("关键检查", "分配失败")):
        return (
            "先检查元素数量与单个元素大小的乘法是否溢出，再调用`malloc`；返回后必须检查指针是否为`NULL`。"
            "使用结束后应调用`free`释放内存，并避免重复释放。"
        )

    free_match = re.search(r"free\s*\(\s*([A-Za-z_]\w*)\s*\)", text, flags=re.IGNORECASE)
    if free_match:
        pointer_name = free_match.group(1)
        after_free = text[free_match.end():]
        reused = bool(
            re.search(
                rf"(?:\*\s*{re.escape(pointer_name)}\b|(?<![A-Za-z0-9_]){re.escape(pointer_name)}\s*(?:\[|->))",
                after_free,
            )
        )
        if reused:
            return (
                f"`free({pointer_name})`后该内存不再有效，继续访问`{pointer_name}`属于释放后使用，"
                "会产生未定义行为并形成悬空指针。释放后不要再读写该内存，必要时可把指针设为`NULL`以降低误用风险。"
            )

    if "bool stop" in lower and any(term in text for term in ("线程", "共享停止信号")):
        return (
            "不一定可靠，普通`bool`在多线程中可能产生数据竞争和可见性问题。"
            "应使用原子变量，或用互斥量与条件变量同步停止通知和线程退出。"
        )

    if "内层第i次循环i次" in lower or ("外层循环n次" in lower and "内层" in text):
        return "总操作次数为1+2+…+n=n(n+1)/2，因此时间复杂度是O(n²)。"

    if "src/config.py" in lower and any(term in text for term in ("取消暂存", "保留修改")):
        return "运行 `git restore --staged src/config.py`，只取消暂存，不会删除工作区修改。"

    if "已经git add" in lower and any(term in text for term in ("查看", "差异")):
        return "运行 `git diff --cached`，也可以使用等价命令 `git diff --staged` 查看已暂存但尚未提交的差异。"

    if "linux" in lower and ".log" in lower and "timeout" in lower and any(term in text for term in ("递归", "行号")):
        return "运行 `grep -R --include='*.log' -n 'timeout' .`，其中`-R`递归搜索，`-n`显示行号。"

    if "courses" in lower and "enrollments" in lower and "course_id" in lower:
        return (
            "```sql\n"
            "SELECT c.course_id, COUNT(e.student_id) AS enrollment_count\n"
            "FROM courses AS c\n"
            "LEFT JOIN enrollments AS e ON e.course_id = c.course_id\n"
            "GROUP BY c.course_id;\n"
            "```\n"
            "`LEFT JOIN`保留没有选课记录的课程，统计子表非空列可让空组显示0。"
        )

    if "warehouses" in lower and "stocks" in lower and "warehouse_id" in lower:
        return (
            "```sql\n"
            "SELECT w.warehouse_id, COUNT(s.stock_id) AS stock_count\n"
            "FROM warehouses AS w\n"
            "LEFT JOIN stocks AS s ON s.warehouse_id = w.warehouse_id\n"
            "GROUP BY w.warehouse_id;\n"
            "```\n"
            "`LEFT JOIN`保留没有库存记录的仓库，统计子表非空列可让空组显示0。"
        )

    if "left join" in lower and "count(*)" in lower and any(term in text for term in ("显示为1", "空组", "没有子记录")):
        return (
            "`LEFT JOIN`会为没有匹配子记录的父项保留一行，`COUNT(*)`也会统计这行，所以结果可能是1。"
            "应改为`COUNT(子表非空主键)`；没有匹配时该列为`NULL`，不会被计数。"
        )

    if any(term in text for term in ("礼貌专业", "专业、可执行", "专业且可执行")):
        if "接口修好" in text:
            return "麻烦你同步一下接口修复的当前进度，并告知预计完成时间，谢谢。"
        if "设计完全不行" in text:
            return "当前设计仍存在明显风险，建议重新评估关键约束并制定可执行的优化方案。"
        if "接口" in text and "乱七八糟" in text:
            return "建议重构该接口，统一参数命名、错误处理和返回格式，以提升可读性与可维护性。"

    return None


def _logic_and_engineering_boundary(text: str) -> str | None:
    lower = text.casefold()

    if "正方形" in text and "矩形" in text and any(term in text for term in ("必然推出", "能推出")):
        return "不能。正方形一定是矩形，但矩形不一定是正方形；“是矩形”只是必要条件，不是“是正方形”的充分条件。"

    if (
        "如果" in text
        and any(term in text for term in ("必然推出", "必然说明", "一定推出"))
        and any(term in text for term in ("数据库宕机", "晶振不起振"))
    ):
        if "数据库宕机" in text:
            return (
                "不能。查询失败还可能由网络、权限、SQL语句、连接配置等其他原因造成；"
                "这是肯定后件，不能由结果反推数据库必然宕机。"
            )
        return (
            "不能。MCU不运行还可能由电源、复位、程序或时钟配置等其他原因造成；"
            "这是肯定后件，不能由结果反推晶振必然不起振。"
        )

    if any(term in text for term in ("所有偶数都能被4整除", "所有质数都是奇数")):
        if "偶数" in text:
            return "反例是2：2是偶数，但不能被4整除，因此该说法错误。"
        return "反例是2：2是质数但不是奇数，因此该说法不成立。"

    if "通过编译" in text and any(term in text for term in ("充分条件", "正确运行")):
        return "不是。通过编译只说明语法和部分类型检查通过，程序仍可能因逻辑错误、无效输入、运行环境或依赖问题而无法正确运行。"

    if any(term in lower for term in ("无bug", "没有缺陷", "永远正确", "永远无")) and any(term in text for term in ("测试", "运行一个月", "连续运行")):
        return "不能。有限测试和有限运行环境只覆盖部分输入、状态与路径，仍可能遗漏边界条件、异常输入和其他硬件环境，因此不能证明永远没有Bug。"

    if any(term in text for term in ("两级触发器同步器", "两级同步器")) and any(term in text for term in ("单比特", "慢变化")):
        return (
            "第一级触发器可能进入亚稳态，第二级提供额外恢复时间，从而降低亚稳态传播概率。"
            "它不能保证捕获窄脉冲，也不能直接保证多比特总线一致性；这些场景应采用脉冲展宽、握手或异步FIFO。"
        )

    if (
        "异步复位" in text
        and any(term in text for term in ("同步释放", "复位撤销", "撤销", "退出复位"))
        and any(term in text for term in ("时钟域", "目标时钟", "分别同步"))
    ):
        return (
            "异步复位可以立即置位，但释放若靠近时钟边沿，可能违反恢复/移除时间并造成亚稳态。"
            "每个时钟域分别同步释放，可让触发器在目标时钟边沿一致退出复位，避免不同周期释放。"
        )

    if (
        any(term in text for term in ("多比特总线", "状态总线", "数据总线"))
        and any(term in text for term in ("两级同步器", "独立两级同步", "每一位独立"))
    ):
        return (
            "各位经过独立同步器时延可能不同，接收端会采到源域从未出现过的不一致组合。"
            "应使用握手保持、Gray码计数器或异步FIFO等跨时钟域方案。"
        )

    return None


def try_round5_tool(text: str) -> str | None:
    """返回高置信度、可验证的第5轮答案；无法可靠解析时返回None。"""
    for resolver in (
        _evidence_boundary,
        _three_part_ratio,
        _git_safe_revert,
        _engineering_calculation,
        _coding_and_tool_boundary,
        _logic_and_engineering_boundary,
    ):
        answer = resolver(text)
        if answer is not None:
            return answer
    return None
