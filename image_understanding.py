"""彦博图片文字识别模块：读取题图、按阅读顺序提取文字并提供置信度。"""

from __future__ import annotations

import io
import threading
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from PIL import Image, ImageEnhance, ImageOps, UnidentifiedImageError


MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_IMAGE_SIDE = 2600
MIN_IMAGE_SIDE = 900
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP", "BMP"}


@dataclass(frozen=True)
class OCRLine:
    text: str
    confidence: float
    box: list[list[float]]


@dataclass(frozen=True)
class OCRResult:
    text: str
    lines: list[OCRLine]
    confidence: float
    width: int
    height: int

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["line_count"] = len(self.lines)
        return result


class ImageRecognitionError(ValueError):
    """图片格式、大小或文字识别失败。"""


class ImageTextRecognizer:
    """延迟加载中文OCR模型，减少普通聊天启动耗时。"""

    _engine: Any | None = None
    _engine_lock = threading.Lock()
    _run_lock = threading.Lock()

    @classmethod
    def _get_engine(cls) -> Any:
        if cls._engine is None:
            with cls._engine_lock:
                if cls._engine is None:
                    try:
                        from rapidocr import RapidOCR
                    except ImportError:
                        try:
                            from rapidocr_onnxruntime import RapidOCR
                        except ImportError as exc:
                            raise RuntimeError(
                                "图片识别组件尚未安装，请先运行 00_setup.bat。"
                            ) from exc
                    try:
                        cls._engine = RapidOCR(params={"Global.log_level": "error"})
                    except TypeError:
                        cls._engine = RapidOCR()
        return cls._engine

    @staticmethod
    def _load_image(image_bytes: bytes) -> Image.Image:
        if not image_bytes:
            raise ImageRecognitionError("图片内容为空。")
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise ImageRecognitionError("图片过大，请上传不超过15MB的图片。")
        try:
            with Image.open(io.BytesIO(image_bytes)) as source:
                source.load()
                if source.format not in SUPPORTED_FORMATS:
                    raise ImageRecognitionError(
                        "暂时只支持 JPG、PNG、WEBP 和 BMP 图片。"
                    )
                image = ImageOps.exif_transpose(source).convert("RGB")
        except ImageRecognitionError:
            raise
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ImageRecognitionError("无法读取这张图片，文件可能已损坏。") from exc
        return image

    @staticmethod
    def _resize_for_ocr(image: Image.Image) -> Image.Image:
        width, height = image.size
        longest = max(width, height)
        shortest = min(width, height)
        if longest > MAX_IMAGE_SIDE:
            scale = MAX_IMAGE_SIDE / longest
            image = image.resize(
                (max(1, round(width * scale)), max(1, round(height * scale))),
                Image.Resampling.LANCZOS,
            )
        elif shortest < MIN_IMAGE_SIDE and longest < 1800:
            scale = min(2.2, MIN_IMAGE_SIDE / max(1, shortest))
            image = image.resize(
                (max(1, round(width * scale)), max(1, round(height * scale))),
                Image.Resampling.LANCZOS,
            )
        return image

    @staticmethod
    def _enhance(image: Image.Image) -> Image.Image:
        gray = ImageOps.grayscale(image)
        gray = ImageOps.autocontrast(gray, cutoff=1)
        gray = ImageEnhance.Contrast(gray).enhance(1.25)
        gray = ImageEnhance.Sharpness(gray).enhance(1.35)
        return gray.convert("RGB")

    @staticmethod
    def _normalize_result(raw_result: Any) -> list[OCRLine]:
        lines: list[OCRLine] = []
        if not raw_result:
            return lines
        for item in raw_result:
            if not isinstance(item, (list, tuple)) or len(item) < 3:
                continue
            box, text, score = item[0], str(item[1]).strip(), item[2]
            if not text:
                continue
            try:
                confidence = float(score)
            except (TypeError, ValueError):
                confidence = 0.0
            normalized_box: list[list[float]] = []
            if isinstance(box, (list, tuple)):
                for point in box:
                    if isinstance(point, (list, tuple)) and len(point) >= 2:
                        normalized_box.append([float(point[0]), float(point[1])])
            lines.append(
                OCRLine(
                    text=text.replace("，", "，").replace(",", "，"),
                    confidence=max(0.0, min(confidence, 1.0)),
                    box=normalized_box,
                )
            )
        return lines

    @staticmethod
    def _line_position(line: OCRLine) -> tuple[float, float]:
        if not line.box:
            return (0.0, 0.0)
        center_y = sum(point[1] for point in line.box) / len(line.box)
        left_x = min(point[0] for point in line.box)
        return (center_y, left_x)

    @classmethod
    def _sort_reading_order(cls, lines: list[OCRLine]) -> list[OCRLine]:
        if len(lines) <= 1:
            return lines
        heights = []
        for line in lines:
            if len(line.box) >= 4:
                heights.append(
                    max(point[1] for point in line.box)
                    - min(point[1] for point in line.box)
                )
        tolerance = max(12.0, (sum(heights) / len(heights)) * 0.55) if heights else 20.0
        sorted_lines = sorted(lines, key=cls._line_position)
        rows: list[list[OCRLine]] = []
        for line in sorted_lines:
            y, _ = cls._line_position(line)
            if not rows:
                rows.append([line])
                continue
            row_y = sum(cls._line_position(item)[0] for item in rows[-1]) / len(rows[-1])
            if abs(y - row_y) <= tolerance:
                rows[-1].append(line)
            else:
                rows.append([line])
        ordered: list[OCRLine] = []
        for row in rows:
            ordered.extend(sorted(row, key=lambda item: cls._line_position(item)[1]))
        return ordered

    @staticmethod
    def _quality(lines: list[OCRLine]) -> float:
        total_chars = sum(len(line.text) for line in lines)
        if total_chars == 0:
            return 0.0
        weighted = sum(len(line.text) * line.confidence for line in lines)
        return weighted / total_chars

    def _run(self, image: Image.Image) -> list[OCRLine]:
        engine = self._get_engine()
        with self._run_lock:
            output = engine(np.asarray(image))

        if hasattr(output, "txts"):
            raw_boxes = getattr(output, "boxes", None)
            raw_texts = getattr(output, "txts", None)
            raw_scores = getattr(output, "scores", None)
            boxes = list(raw_boxes) if raw_boxes is not None else []
            texts = list(raw_texts) if raw_texts is not None else []
            scores = list(raw_scores) if raw_scores is not None else []
            raw_result = [
                [boxes[index] if index < len(boxes) else [], text, scores[index] if index < len(scores) else 0.0]
                for index, text in enumerate(texts)
            ]
        elif isinstance(output, tuple):
            raw_result = output[0]
        else:
            raw_result = output
        return self._sort_reading_order(self._normalize_result(raw_result))

    def recognize_bytes(self, image_bytes: bytes) -> OCRResult:
        original = self._load_image(image_bytes)
        original_width, original_height = original.size
        prepared = self._resize_for_ocr(original)

        primary = self._run(prepared)
        primary_quality = self._quality(primary)
        primary_chars = sum(len(line.text) for line in primary)

        best = primary
        best_quality = primary_quality
        if primary_chars < 10 or primary_quality < 0.78:
            enhanced = self._run(self._enhance(prepared))
            enhanced_quality = self._quality(enhanced)
            if (
                enhanced_quality > best_quality + 0.015
                or sum(len(line.text) for line in enhanced) > primary_chars + 3
            ):
                best = enhanced
                best_quality = enhanced_quality

        text = "\n".join(line.text for line in best).strip()
        if not text:
            raise ImageRecognitionError(
                "没有识别到清晰文字。请尽量拍正、对焦，并保证光线充足。"
            )
        return OCRResult(
            text=text,
            lines=best,
            confidence=best_quality,
            width=original_width,
            height=original_height,
        )
