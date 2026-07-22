"""训练样本质量检查，阻止截断、空洞或带无关寒暄的导师答案进入数据集。"""

from __future__ import annotations

import re
from typing import Any


MAX_TEACHER_ANSWER_CHARS = 900


def extract_training_pair(item: object) -> tuple[str, str] | None:
    if not isinstance(item, dict):
        return None
    messages = item.get("messages", [])
    if not isinstance(messages, list):
        return None
    user = ""
    assistant = ""
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", "")).strip().lower()
        content = str(message.get("content", "")).strip()
        if role == "user":
            user = content
        elif role == "assistant":
            assistant = content
    if not user or not assistant:
        return None
    return user, assistant


def is_training_answer_usable(answer: str) -> bool:
    value = answer.strip()
    if not value or len(value) > MAX_TEACHER_ANSWER_CHARS:
        return False
    if value.count("```") % 2:
        return False
    if re.search(r"(?:您好[，,]?我是|彦博-v\d+为您|明白了您的学习需求)", value[:120]):
        return False
    if re.search(r"[，、：:(（\[{]$", value):
        return False
    if value.endswith(("并且", "以及", "例如", "如下", "包括", "的", "了一个")):
        return False
    return True


def is_teacher_row_usable(item: Any) -> bool:
    pair = extract_training_pair(item)
    return pair is not None and is_training_answer_usable(pair[1])
