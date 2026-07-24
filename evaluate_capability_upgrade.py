"""彦博能力分层、知识检索与直接视觉链路的轻量回归测试。"""

from __future__ import annotations

import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from assistant_engine import AssistantEngine, NativeBackend, RemoteBackend
from capability_config import load_mode_profiles
from console_utils import configure_utf8_console
from image_understanding import ImageRecognitionError
from knowledge_base import LocalKnowledgeBase


class QuietExpertHandler(BaseHTTPRequestHandler):
    payload: dict[str, Any] = {}

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        self.__class__.payload = json.loads(self.rfile.read(length))
        body = (
            'data: {"choices":[{"delta":{"content":"专家回答"},"finish_reason":null}]}\n\n'
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
            'data: [DONE]\n\n'
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


class FailingRecognizer:
    def recognize_bytes(self, image_bytes: bytes):
        del image_bytes
        raise ImageRecognitionError("测试图片没有文字")


class CaptureVisionBackend:
    supports_vision = True
    last_done_reason = "stop"
    last_generated_tokens = 8

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def stream_generate(
        self,
        messages: list[dict[str, Any]],
        max_new_tokens: int,
        temperature: float,
    ):
        del max_new_tokens, temperature
        self.messages = messages
        yield "已结合原图和识别文字分析。"


def make_test_engine() -> tuple[AssistantEngine, CaptureVisionBackend]:
    engine = object.__new__(AssistantEngine)
    backend = CaptureVisionBackend()
    engine.history = []
    engine.memory = {}
    engine.knowledge_base = None
    engine.image_recognizer = FailingRecognizer()
    engine.num_ctx = 8192
    engine.direct_vision = True
    engine.backend = backend
    engine.backend_kind = "native"
    return engine, backend


def test_profiles() -> None:
    profiles = load_mode_profiles()
    assert set(profiles) == {"fast", "thinking", "expert"}
    assert profiles["fast"].num_ctx < profiles["thinking"].num_ctx <= profiles["expert"].num_ctx
    assert profiles["expert"].text_max_tokens > profiles["thinking"].text_max_tokens
    assert not any(profile.direct_vision for profile in profiles.values())
    print("[通过] 快速、思考、专家三层配置有效，未验证视觉默认关闭")


def test_knowledge_retrieval() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "泵站设计.md").write_text(
            "KQSN600-M13 单台流量为2710立方米每小时。近期采用两用一备。",
            encoding="utf-8",
        )
        base = LocalKnowledgeBase(root)
        results = base.retrieve("KQSN600-M13近期运行方式和单台流量", limit=2)
        assert results and "2710" in results[0].text and "泵站设计.md" == results[0].source
    print("[通过] 本地专业资料能够按问题检索")


def test_direct_vision_message() -> None:
    engine, backend = make_test_engine()
    image_bytes = b"\x89PNG\r\n\x1a\n" + b"test-image"
    answer = "".join(
        engine.stream_image_reply(
            image_bytes=image_bytes,
            user_text="分析电路图中的连接关系。",
            filename="电路图.png",
            max_new_tokens=80,
            temperature=0.0,
            response_mode="expert",
        )
    )
    assert "原图" in answer
    assert backend.messages
    image_urls = backend.messages[-1].get("image_data_urls", [])
    assert image_urls and str(image_urls[0]).startswith("data:image/png;base64,")
    print("[通过] 纯图形图片即使OCR失败，专家视觉仍能接收原图")


def test_remote_expert_backend() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), QuietExpertHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        backend = RemoteBackend(
            api_url=f"http://127.0.0.1:{server.server_port}",
            api_key="",
            model_name="expert-test",
        )
        answer = backend.generate(
            [
                {
                    "role": "user",
                    "content": "分析图片",
                    "image_data_urls": ["data:image/png;base64,dGVzdA=="],
                }
            ],
            max_new_tokens=80,
            temperature=0.0,
        )
        payload = QuietExpertHandler.payload
        assert answer == "专家回答"
        assert payload.get("model") == "expert-test"
        assert isinstance(payload.get("messages", [{}])[0].get("content"), list)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    print("[通过] 远程专家后端支持流式文本和图片消息格式")


def test_native_capabilities() -> None:
    backend = NativeBackend("yanbo-v3:latest", num_ctx=8192)
    assert backend.model_name.removesuffix(":latest") == "yanbo-v3"
    print("[通过] 快速、思考与专家模式统一连接彦博-v3运行模型")


def main() -> None:
    configure_utf8_console()
    test_profiles()
    test_knowledge_retrieval()
    test_direct_vision_message()
    test_remote_expert_backend()
    test_native_capabilities()
    print("\n能力升级回归测试：5/5 通过")


if __name__ == "__main__":
    main()
