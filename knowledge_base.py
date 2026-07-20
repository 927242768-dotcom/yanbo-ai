"""轻量本地知识库：从 knowledge/ 中检索与问题最相关的文本片段。"""

from __future__ import annotations

import json
import math
import re
import threading
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
DEFAULT_KNOWLEDGE_DIR = ROOT / "knowledge"
SUPPORTED_SUFFIXES = {
    ".txt",
    ".md",
    ".json",
    ".jsonl",
    ".csv",
    ".py",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".js",
    ".ts",
    ".java",
    ".sql",
}
MAX_FILE_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class KnowledgeChunk:
    source: str
    text: str
    terms: Counter[str]


@dataclass(frozen=True)
class RetrievedChunk:
    source: str
    text: str
    score: float


def _terms(text: str) -> list[str]:
    normalized = text.lower()
    latin = re.findall(r"[a-z_][a-z0-9_+#.:-]{1,40}|\d+(?:\.\d+)?", normalized)
    chinese_runs = re.findall(r"[\u4e00-\u9fff]{2,}", normalized)
    chinese: list[str] = []
    for run in chinese_runs:
        if len(run) <= 4:
            chinese.append(run)
        chinese.extend(run[index:index + 2] for index in range(len(run) - 1))
    return latin + chinese


def _split_text(text: str, max_chars: int = 1500, overlap: int = 180) -> Iterable[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    buffer = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if buffer:
                yield buffer.strip()
                buffer = ""
            start = 0
            while start < len(paragraph):
                chunk = paragraph[start:start + max_chars].strip()
                if chunk:
                    yield chunk
                start += max(1, max_chars - overlap)
            continue
        candidate = paragraph if not buffer else buffer + "\n\n" + paragraph
        if len(candidate) <= max_chars:
            buffer = candidate
            continue
        if buffer:
            yield buffer.strip()
            tail = buffer[-overlap:].strip()
            buffer = (tail + "\n\n" + paragraph).strip() if tail else paragraph
        else:
            buffer = paragraph
    if buffer:
        yield buffer.strip()


def _json_to_text(value: object) -> str:
    if isinstance(value, dict):
        rows = []
        for key, item in value.items():
            rendered = _json_to_text(item)
            if rendered:
                rows.append(f"{key}: {rendered}")
        return "\n".join(rows)
    if isinstance(value, list):
        return "\n".join(_json_to_text(item) for item in value if item is not None)
    if value is None:
        return ""
    return str(value)


class LocalKnowledgeBase:
    """按文件更新时间缓存索引，使用词频和逆文档频率进行本地检索。"""

    def __init__(self, directory: str | Path = DEFAULT_KNOWLEDGE_DIR) -> None:
        self.directory = Path(directory)
        self._lock = threading.Lock()
        self._signature: tuple[tuple[str, int, int], ...] = ()
        self._chunks: list[KnowledgeChunk] = []
        self._document_frequency: Counter[str] = Counter()

    def _files(self) -> list[Path]:
        if not self.directory.exists():
            return []
        files = []
        for path in self.directory.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            if path.name.lower() in {"readme.md", ".gitkeep"}:
                continue
            try:
                if path.stat().st_size <= MAX_FILE_BYTES:
                    files.append(path)
            except OSError:
                continue
        return sorted(files)

    def _current_signature(self, files: list[Path]) -> tuple[tuple[str, int, int], ...]:
        rows = []
        for path in files:
            try:
                stat = path.stat()
            except OSError:
                continue
            rows.append((str(path.relative_to(self.directory)), stat.st_mtime_ns, stat.st_size))
        return tuple(rows)

    @staticmethod
    def _read_text(path: Path) -> str:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        suffix = path.suffix.lower()
        if suffix == ".json":
            try:
                return _json_to_text(json.loads(raw))
            except (ValueError, TypeError):
                return raw
        if suffix == ".jsonl":
            rows = []
            for line in raw.splitlines():
                if not line.strip():
                    continue
                try:
                    rows.append(_json_to_text(json.loads(line)))
                except (ValueError, TypeError):
                    rows.append(line)
            return "\n".join(rows)
        return raw

    def _rebuild_if_needed(self) -> None:
        files = self._files()
        signature = self._current_signature(files)
        if signature == self._signature:
            return
        with self._lock:
            files = self._files()
            signature = self._current_signature(files)
            if signature == self._signature:
                return
            chunks: list[KnowledgeChunk] = []
            document_frequency: Counter[str] = Counter()
            for path in files:
                source = str(path.relative_to(self.directory)).replace("\\", "/")
                text = self._read_text(path)
                for chunk_text in _split_text(text):
                    counts = Counter(_terms(chunk_text))
                    if not counts:
                        continue
                    chunks.append(KnowledgeChunk(source=source, text=chunk_text, terms=counts))
                    document_frequency.update(counts.keys())
            self._chunks = chunks
            self._document_frequency = document_frequency
            self._signature = signature

    def retrieve(
        self,
        query: str,
        limit: int = 4,
        max_total_chars: int = 6000,
    ) -> list[RetrievedChunk]:
        query_counts = Counter(_terms(query))
        if not query_counts:
            return []
        self._rebuild_if_needed()
        total_chunks = len(self._chunks)
        if total_chunks == 0:
            return []

        scored: list[RetrievedChunk] = []
        query_length = max(1, sum(query_counts.values()))
        for chunk in self._chunks:
            score = 0.0
            for term, query_frequency in query_counts.items():
                chunk_frequency = chunk.terms.get(term, 0)
                if not chunk_frequency:
                    continue
                document_frequency = self._document_frequency.get(term, 0)
                inverse_document_frequency = math.log(
                    1 + (total_chunks + 1) / (document_frequency + 1)
                )
                score += (
                    min(3, query_frequency)
                    * (1 + math.log(1 + chunk_frequency))
                    * inverse_document_frequency
                )
            if score <= 0:
                continue
            length_penalty = 1 + max(0, len(chunk.text) - 900) / 4000
            normalized = score / (math.sqrt(query_length) * length_penalty)
            scored.append(
                RetrievedChunk(source=chunk.source, text=chunk.text, score=normalized)
            )

        selected: list[RetrievedChunk] = []
        total_chars = 0
        seen_text: set[str] = set()
        for item in sorted(scored, key=lambda value: value.score, reverse=True):
            fingerprint = re.sub(r"\s+", " ", item.text[:220]).strip().lower()
            if fingerprint in seen_text:
                continue
            if selected and item.score < selected[0].score * 0.22:
                break
            remaining = max_total_chars - total_chars
            if remaining <= 0:
                break
            text = item.text[:remaining]
            selected.append(RetrievedChunk(item.source, text, item.score))
            seen_text.add(fingerprint)
            total_chars += len(text)
            if len(selected) >= max(1, limit):
                break
        return selected
