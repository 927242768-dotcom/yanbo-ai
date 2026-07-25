"""解析用户对数量、长度和输出形式的硬约束，并在生成后进行轻量校正。"""

from __future__ import annotations

import re
from dataclasses import dataclass


_CHINESE_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
_NUMBER = r"(?:\d{1,2}|[一二两三四五六七八九十]{1,3})"
_LIST_MARKER = re.compile(
    r"(?m)^\s*(?:\d{1,2}[.、)）]|[一二三四五六七八九十]{1,3}[、.）)]|[-*•])\s*"
)
# 中文句号后通常直接连接下一句，不应要求标点后必须有空白。
_SENTENCE = re.compile(r".+?(?:[。！？!?]|$)", re.S)


@dataclass(frozen=True)
class ResponseContract:
    exact_items: int | None = None
    exact_sentences: int | None = None
    concise: bool = False
    direct_output: bool = False
    rewrite_only: bool = False
    max_new_tokens: int | None = None

    @property
    def requires_buffering(self) -> bool:
        return bool(
            self.exact_items is not None
            or self.exact_sentences is not None
            or self.direct_output
            or self.rewrite_only
        )

    @property
    def allow_continuation(self) -> bool:
        return not self.requires_buffering and not self.concise

    def system_instruction(self) -> str:
        rules: list[str] = []
        if self.exact_items is not None:
            rules.append(
                f"必须恰好输出{self.exact_items}项；使用清晰编号；每项必须包含具体、完整的正文，"
                f"不得只写序号；不得增加前言、总结或第{self.exact_items + 1}项。"
            )
        if self.exact_sentences is not None:
            rules.append(
                f"必须恰好输出{self.exact_sentences}句话；不要用标题、项目符号或额外说明。"
            )
        if self.rewrite_only:
            rules.append("只输出改写后的成品文本，不解释修改理由，不提供多个版本。")
        elif self.direct_output:
            rules.append("直接输出用户要求的成品，不添加寒暄、前言、选择建议或总结。")
        if self.concise:
            rules.append("保持简洁，只保留回答问题所需的信息。")
        if not rules:
            return ""
        return "\n本次回答的硬约束（优先级高于一般表达习惯）：\n- " + "\n- ".join(rules)


def _parse_number(value: str) -> int | None:
    value = value.strip()
    if value.isdigit():
        number = int(value)
        return number if 1 <= number <= 20 else None
    if value in _CHINESE_DIGITS:
        return _CHINESE_DIGITS[value]
    if value.startswith("十") and len(value) == 2 and value[1] in _CHINESE_DIGITS:
        return 10 + _CHINESE_DIGITS[value[1]]
    if value.endswith("十") and len(value) == 2 and value[0] in _CHINESE_DIGITS:
        return _CHINESE_DIGITS[value[0]] * 10
    if "十" in value and len(value) == 3:
        left, right = value.split("十", 1)
        if left in _CHINESE_DIGITS and right in _CHINESE_DIGITS:
            return _CHINESE_DIGITS[left] * 10 + _CHINESE_DIGITS[right]
    return None


def _first_number(patterns: list[str], text: str) -> int | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            number = _parse_number(match.group("count"))
            if number is not None:
                return number
    return None


def analyze_response_contract(text: str) -> ResponseContract:
    normalized = re.sub(r"\s+", " ", text.strip())

    sentence_count = _first_number(
        [
            rf"(?P<count>{_NUMBER})\s*句(?:话)?",
            rf"(?:用|控制在|限制为)\s*(?P<count>{_NUMBER})\s*句",
        ],
        normalized,
    )

    item_count = _first_number(
        [
            rf"(?:只|仅|请)?\s*(?:给我|给出|列出|提供|写出|生成|总结出|说明)\s*(?:恰好|正好|只能|必须)?\s*(?P<count>{_NUMBER})\s*(?:个|条|点|项|种|阶段|步骤|标题|建议|办法|原因|例子|要点|方案)",
            rf"(?P<count>{_NUMBER})\s*(?:个|条|点|项|种)?\s*[^，。！？!?]{{0,12}}(?:建议|办法|原因|例子|要点|方案)",
            rf"(?P<count>{_NUMBER})\s*(?:个|条|点|项|种)?\s*(?:阶段|步骤|标题)",
        ],
        normalized,
    )

    rewrite_only = bool(
        re.search(r"(?:改得|改成|改写|润色|重写|优化表达|变得更礼貌)", normalized)
    ) and not bool(re.search(r"(?:解释|说明)(?:为什么|修改理由)", normalized))

    explicit_direct = bool(
        re.search(
            r"(?:只|仅)(?:能)?(?:给|要|输出|写|返回)|不要(?:解释|展开|前言|总结)|直接(?:给|输出|写)|只要标题",
            normalized,
        )
    )
    concise = bool(
        re.search(r"简洁|简短|精简|一句话|两句话|不要啰嗦|别展开|控制在\s*\d+\s*字", normalized)
    ) or explicit_direct

    max_tokens: int | None = None
    if rewrite_only:
        max_tokens = 180
    if sentence_count is not None:
        max_tokens = min(max_tokens or 8192, max(80, sentence_count * 90))
    if item_count is not None:
        max_tokens = min(max_tokens or 8192, max(160, item_count * 120 + 40))
    if concise:
        max_tokens = min(max_tokens or 8192, 320)

    return ResponseContract(
        exact_items=item_count,
        exact_sentences=sentence_count,
        concise=concise,
        direct_output=explicit_direct,
        rewrite_only=rewrite_only,
        max_new_tokens=max_tokens,
    )


def _deduplicate_adjacent_blocks(text: str) -> str:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    result: list[str] = []
    for block in blocks:
        fingerprint = re.sub(r"\s+", " ", block).strip().lower()
        if result:
            previous = re.sub(r"\s+", " ", result[-1]).strip().lower()
            if fingerprint == previous:
                continue
        result.append(block)
    return "\n\n".join(result)


def _strip_preamble(text: str) -> str:
    value = text.strip()
    value = re.sub(
        r"^(?:好的|当然可以|可以|以下是|推荐改为|可改为|修改为|润色后)[：:，,。！!\s]*",
        "",
        value,
        count=1,
    )
    return value.strip()


def _trim_items(text: str, count: int) -> str:
    matches = list(_LIST_MARKER.finditer(text))
    if matches:
        segments: list[str] = []
        for index, match in enumerate(matches[:count]):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            body = text[match.end():end].strip()
            if body:
                segments.append(f"{index + 1}. {body}")
        if segments:
            return "\n".join(segments[:count]).strip()

    lines = [line.strip(" -*•\t") for line in text.splitlines() if line.strip()]
    if len(lines) >= count:
        return "\n".join(f"{index}. {line}" for index, line in enumerate(lines[:count], start=1))

    parts = [part.strip() for part in re.split(r"[；;](?:\s*)", text) if part.strip()]
    if len(parts) >= count:
        return "\n".join(f"{index}. {part.rstrip('。.!！')}。" for index, part in enumerate(parts[:count], start=1))
    return text.strip()


def _trim_sentences(text: str, count: int) -> str:
    sentences = [match.group(0).strip() for match in _SENTENCE.finditer(text) if match.group(0).strip()]
    if len(sentences) >= count:
        return "".join(sentences[:count]).strip()

    # 模型有时用分号或换行分隔多个完整语义段，但只在最后使用句号。
    # 对明确要求固定句数的任务，把这些段落规范为独立句子。
    clauses = [
        clause.strip().rstrip("。！？!?；;")
        for clause in re.split(r"[；;]+|\n+", text)
        if clause.strip().rstrip("。！？!?；;")
    ]
    if len(clauses) >= count:
        return "".join(f"{clause}。" for clause in clauses[:count])
    return text.strip()


def response_contract_satisfied(text: str, contract: ResponseContract) -> bool:
    if contract.exact_items is not None:
        markers = list(_LIST_MARKER.finditer(text))
        if len(markers) != contract.exact_items:
            return False
        for index, marker in enumerate(markers):
            end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
            if not text[marker.end():end].strip():
                return False
    if contract.exact_sentences is not None:
        sentences = [
            match.group(0).strip()
            for match in _SENTENCE.finditer(text)
            if match.group(0).strip()
        ]
        if len(sentences) != contract.exact_sentences:
            return False
    return True


def enforce_response_contract(text: str, contract: ResponseContract) -> str:
    value = _deduplicate_adjacent_blocks(text.strip())
    if contract.rewrite_only or contract.direct_output:
        value = _strip_preamble(value)

    if contract.exact_items is not None:
        value = _trim_items(value, contract.exact_items)
    if contract.exact_sentences is not None:
        value = _trim_sentences(value, contract.exact_sentences)

    if contract.rewrite_only:
        matches = list(_LIST_MARKER.finditer(value))
        if matches:
            start = matches[0].end()
            end = matches[1].start() if len(matches) > 1 else len(value)
            value = value[start:end].strip()
        value = re.sub(r"^(?:[“\"'])(.*)(?:[”\"'])$", r"\1", value.strip(), flags=re.S)
        explanation = re.search(r"\n\s*(?:说明|理由|修改说明|这样写)[：:]", value)
        if explanation:
            value = value[: explanation.start()].strip()

    return value.strip()
