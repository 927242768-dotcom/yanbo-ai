"""从高质量训练样本中检索相似示例，让主力运行模型直接受训练数据影响。"""

from __future__ import annotations

import json
import math
import re
import threading
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = ROOT / "data" / "quality_sft_train.jsonl"
MAX_EXAMPLE_CHARS = 900
_STOP_TERMS = {
    "请",
    "一下",
    "一个",
    "给出",
    "说明",
    "解释",
    "什么",
    "怎么",
    "如何",
    "可以",
    "需要",
    "这个",
    "用户",
}


@dataclass(frozen=True)
class BehaviorExample:
    user: str
    assistant: str
    terms: Counter[str]


@dataclass(frozen=True)
class RetrievedBehaviorExample:
    user: str
    assistant: str
    score: float


def _terms(text: str) -> list[str]:
    normalized = text.lower()
    terms = re.findall(r"[a-z_][a-z0-9_+#.:-]{1,40}|\d+(?:\.\d+)?", normalized)
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", normalized):
        if len(run) <= 5:
            terms.append(run)
        terms.extend(run[index:index + 2] for index in range(len(run) - 1))
    return [term for term in terms if term not in _STOP_TERMS]


def _extract_pair(item: object) -> tuple[str, str] | None:
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


def is_behavior_example_usable(user: str, assistant: str) -> bool:
    if len(user) > 600 or len(assistant) > MAX_EXAMPLE_CHARS:
        return False
    if assistant.count("```") % 2:
        return False
    if re.search(r"(?:您好[，,]?我是|彦博-v\d+为您|下面为您|明白了您的学习需求)", assistant[:100]):
        return False
    if re.search(r"[，、：:(（\[{]$", assistant.rstrip()):
        return False
    if assistant.rstrip().endswith(("并且", "以及", "例如", "如下", "包括")):
        return False
    return True


class BehaviorExampleLibrary:
    """按数据文件更新时间建立内存索引，检索少量高相关示例。"""

    def __init__(self, dataset: str | Path = DEFAULT_DATASET) -> None:
        self.dataset = Path(dataset)
        self._lock = threading.Lock()
        self._signature: tuple[int, int] = (0, 0)
        self._examples: list[BehaviorExample] = []
        self._document_frequency: Counter[str] = Counter()

    def _current_signature(self) -> tuple[int, int]:
        try:
            stat = self.dataset.stat()
        except OSError:
            return (0, 0)
        return stat.st_mtime_ns, stat.st_size

    def _rebuild_if_needed(self) -> None:
        signature = self._current_signature()
        if signature == self._signature:
            return
        with self._lock:
            signature = self._current_signature()
            if signature == self._signature:
                return
            examples: list[BehaviorExample] = []
            document_frequency: Counter[str] = Counter()
            if self.dataset.exists():
                try:
                    lines = self.dataset.read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    lines = []
                for line in lines:
                    if not line.strip():
                        continue
                    try:
                        pair = _extract_pair(json.loads(line))
                    except (ValueError, TypeError):
                        continue
                    if pair is None:
                        continue
                    user, assistant = pair
                    if not is_behavior_example_usable(user, assistant):
                        continue
                    counts = Counter(_terms(user))
                    if not counts:
                        continue
                    examples.append(BehaviorExample(user=user, assistant=assistant, terms=counts))
                    document_frequency.update(counts.keys())
            self._examples = examples
            self._document_frequency = document_frequency
            self._signature = signature

    def retrieve(
        self,
        query: str,
        limit: int = 2,
        max_total_chars: int = 1200,
    ) -> list[RetrievedBehaviorExample]:
        query_counts = Counter(_terms(query))
        if not query_counts:
            return []
        self._rebuild_if_needed()
        total = len(self._examples)
        if total == 0:
            return []

        scored: list[RetrievedBehaviorExample] = []
        for example in self._examples:
            overlap = set(query_counts).intersection(example.terms)
            if len(overlap) < 2:
                continue
            score = 0.0
            for term in overlap:
                document_frequency = self._document_frequency.get(term, 0)
                inverse_document_frequency = math.log(1 + (total + 1) / (document_frequency + 1))
                score += min(2, query_counts[term]) * inverse_document_frequency
            query_coverage = len(overlap) / max(1, len(query_counts))
            example_coverage = len(overlap) / max(1, len(example.terms))
            score *= 0.65 + query_coverage + 0.35 * example_coverage
            if query.strip() == example.user.strip():
                score += 100
            scored.append(
                RetrievedBehaviorExample(
                    user=example.user,
                    assistant=example.assistant,
                    score=score,
                )
            )

        if not scored:
            return []
        ranked = sorted(scored, key=lambda item: item.score, reverse=True)
        best = ranked[0].score
        selected: list[RetrievedBehaviorExample] = []
        total_chars = 0
        for item in ranked:
            if selected and item.score < best * 0.45:
                break
            size = len(item.user) + len(item.assistant)
            if total_chars + size > max_total_chars:
                continue
            selected.append(item)
            total_chars += size
            if len(selected) >= max(1, limit):
                break
        return selected
