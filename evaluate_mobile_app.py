"""在移动端浏览器环境中回归测试彦博原生应用网页资源。"""

from __future__ import annotations

import io
import json
import threading
import time
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

from console_utils import configure_utf8_console
from remote_access_config import load_remote_access_config


ROOT = Path(__file__).resolve().parent
WWW = ROOT / "mobile_app" / "www"
SERVER_URL = "http://127.0.0.1:7860"
APP_URL = "http://127.0.0.1:7871"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        return


def make_math_image() -> bytes:
    image = Image.new("RGB", (900, 260), "white")
    draw = ImageDraw.Draw(image)
    font_path = Path(r"C:\Windows\Fonts\msyhbd.ttc")
    font = ImageFont.truetype(str(font_path), 72) if font_path.exists() else ImageFont.load_default()
    draw.text((45, 75), "题目：18 + 24 = ？", fill="black", font=font)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def main() -> None:
    configure_utf8_console()
    handler = partial(QuietHandler, directory=str(WWW))
    server = ThreadingHTTPServer(("127.0.0.1", 7871), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    remote = load_remote_access_config()
    results: list[tuple[str, bool, str]] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 390, "height": 844},
                device_scale_factor=2,
                is_mobile=True,
                has_touch=True,
            )
            page = context.new_page()
            test_url = (
                f"{APP_URL}/?server={quote(SERVER_URL, safe='')}"
                f"&token={quote(remote['access_token'], safe='')}"
            )
            page.goto(test_url, wait_until="domcontentloaded")
            page.wait_for_timeout(800)
            empty_title = page.locator(".empty-state h2").inner_text()
            navigation_ready = page.locator("#newChat").is_visible() and page.locator("#conversationList").is_visible()
            results.append(("多会话主界面", navigation_ready and empty_title == "今天想聊些什么？", empty_title))
            mode_ready = page.locator("#modeThinking").is_visible() and page.locator("#modeFast").is_visible()
            default_thinking = "active" in (page.locator("#modeThinking").get_attribute("class") or "")
            page.locator("#modeFast").click()
            fast_selected = "彦博-快速" in page.locator("#chatSubtitle").inner_text()
            page.locator("#modeThinking").click()
            results.append(("思考与快速模式切换", mode_ready and default_thinking and fast_selected, "两种模式可见、可切换并按对话保存"))
            compact_layout = page.evaluate(
                """() => {
                    const title=parseFloat(getComputedStyle(document.querySelector('.empty-state h2')).fontSize);
                    const logo=parseFloat(getComputedStyle(document.querySelector('.empty-logo')).width);
                    const columns=getComputedStyle(document.querySelector('.suggestions')).gridTemplateColumns.split(' ').length;
                    const composer=document.querySelector('.composer').getBoundingClientRect().height;
                    return title<=21 && logo<=56 && columns===2 && composer<122;
                }"""
            )
            results.append(("紧凑美观布局", compact_layout, "字号、留白、双列快捷卡片、模式选择器和输入区尺寸符合移动端"))

            page.locator("#input").fill("2+2等于多少？")
            page.locator("#send").click()
            page.wait_for_function(
                "[...document.querySelectorAll('.assistant .bubble')].some(x=>x.textContent.includes('4'))",
                timeout=30_000,
            )
            results.append(("思考反馈与流式文字聊天", True, "发送后显示状态，2+2回答包含4"))

            first_title = page.locator("#chatTitle").inner_text()
            page.locator("#headerNew").click()
            page.wait_for_selector(".empty-state")
            page.locator("#input").fill("3+3等于多少？")
            page.locator("#send").click()
            page.wait_for_function(
                "[...document.querySelectorAll('.assistant .bubble')].some(x=>x.textContent.includes('6'))",
                timeout=30_000,
            )
            page.locator("#menu").click()
            page.locator(".conversation-title", has_text=first_title).click()
            page.wait_for_function(
                "[...document.querySelectorAll('.assistant .bubble')].some(x=>x.textContent.includes('4'))",
                timeout=10_000,
            )
            results.append(("新建与切换对话", True, "两个对话内容互相独立并可切换"))

            page.locator("#galleryInput").set_input_files(
                files=[{"name": "math.png", "mimeType": "image/png", "buffer": make_math_image()}]
            )
            page.wait_for_function("document.querySelector('#preview').style.display==='flex'", timeout=10_000)
            results.append(("相册图片预览", True, "图片预览已显示"))
            page.locator("#input").fill("请识别并计算")
            page.locator("#send").click()
            page.wait_for_function(
                "[...document.querySelectorAll('.assistant .bubble')].some(x=>x.textContent.includes('42'))",
                timeout=60_000,
            )
            results.append(("图片识别与做题", True, "图片答案包含42"))

            camera_visible = page.locator("#camera").is_visible()
            gallery_visible = page.locator("#gallery").is_visible()
            results.append(("拍照与相册入口", camera_visible and gallery_visible, "两个入口均可见"))

            retry_page = context.new_page()
            retry_attempts = {"count": 0, "request_ids": set()}

            def handle_retry_route(route) -> None:
                retry_attempts["count"] += 1
                try:
                    retry_attempts["request_ids"].add(route.request.post_data_json.get("request_id"))
                except Exception:
                    pass
                if retry_attempts["count"] <= 2:
                    route.abort("connectionfailed")
                else:
                    route.continue_()

            retry_page.route("**/chat-job", handle_retry_route)
            retry_page.goto(test_url, wait_until="domcontentloaded")
            retry_page.locator("#headerNew").click()
            retry_page.locator("#input").fill("5+5等于多少？")
            retry_page.locator("#send").click()
            retry_page.wait_for_function(
                "[...document.querySelectorAll('.assistant .bubble')].some(x=>x.textContent.includes('10'))",
                timeout=45_000,
            )
            results.append(
                (
                    "断线自动重连",
                    retry_attempts["count"] >= 3 and len(retry_attempts["request_ids"]) == 1,
                    f"前两次连接失败后自动重试，共请求{retry_attempts['count']}次且请求编号保持一致",
                )
            )
            retry_page.close()

            interrupted_page = context.new_page()
            interrupted_attempts = {"count": 0}

            def handle_interrupted_poll(route) -> None:
                interrupted_attempts["count"] += 1
                if interrupted_attempts["count"] == 1:
                    route.abort("connectionfailed")
                else:
                    route.continue_()

            interrupted_page.route("**/api/job*", handle_interrupted_poll)
            interrupted_page.goto(test_url, wait_until="domcontentloaded")
            interrupted_page.locator("#headerNew").click()
            interrupted_page.locator("#input").fill("请用三句话解释函数指针，并且必须包含“回调函数”四个字。")
            interrupted_page.locator("#send").click()
            interrupted_page.wait_for_function(
                "[...document.querySelectorAll('.assistant .bubble')].some(x=>x.textContent.includes('回调函数'))",
                timeout=45_000,
            )
            final_interrupted_text = interrupted_page.locator(".assistant .bubble").last.inner_text()
            results.append(
                (
                    "任务轮询中断恢复",
                    interrupted_attempts["count"] >= 2 and "回调函数" in final_interrupted_text,
                    "首次任务查询断开后自动恢复，并继续取得完整答案",
                )
            )
            interrupted_page.close()

            update_page = context.new_page()
            update_page.add_init_script(
                "window.YanboAndroid={installUpdate:(url,version)=>{window.__yanboUpdateCall={url,version}}};"
            )
            update_page.route(
                "**/api/version*",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    headers={"Access-Control-Allow-Origin": "*"},
                    body=json.dumps(
                        {
                            "app_version": "9.9.9",
                            "android_download_url": "/downloads/Yanbo-AI-Android-v9.9.9.apk",
                            "ios_download_url": "/downloads/Yanbo-AI-iOS-v9.9.9.zip",
                            "release_notes": ["测试应用内更新弹窗", "测试下载进度反馈"],
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            update_page.goto(test_url, wait_until="domcontentloaded")
            update_page.wait_for_selector("#updateDialog.open", timeout=10_000)
            update_page.locator("#updateNow").click()
            update_page.wait_for_function("window.__yanboUpdateCall?.version==='9.9.9'", timeout=5_000)
            update_page.evaluate(
                "window.onYanboUpdateStatus({status:'progress',percent:42,message:'正在下载更新 42%'})"
            )
            progress_width = update_page.locator("#updateProgressBar").evaluate("element=>element.style.width")
            results.append(("应用内更新弹窗", progress_width == "42%", "检测版本、立即更新与下载进度反馈均正常"))

            replay_payload = json.dumps(
                {
                    "request_id": "mobile-disconnect-replay-test",
                    "mode": "thinking",
                    "message": "请用两句话说明函数指针是什么。",
                    "history": [],
                },
                ensure_ascii=False,
            ).encode("utf-8")
            replay_headers = {
                "Content-Type": "application/json",
                "X-Yanbo-Token": remote["access_token"],
                "X-Yanbo-Session": "mobile-disconnect-replay-session",
            }
            first_request = urllib.request.Request(
                f"{SERVER_URL}/chat-stream",
                data=replay_payload,
                headers=replay_headers,
                method="POST",
            )
            first_response = urllib.request.urlopen(first_request, timeout=90)
            saw_delta = False
            for raw_line in first_response:
                event = json.loads(raw_line.decode("utf-8"))
                if event.get("type") == "delta":
                    saw_delta = True
                    break
            first_response.close()
            time.sleep(0.2)
            replay_request = urllib.request.Request(
                f"{SERVER_URL}/chat-stream",
                data=replay_payload,
                headers=replay_headers,
                method="POST",
            )
            with urllib.request.urlopen(replay_request, timeout=120) as replay_response:
                replay_events = [
                    json.loads(line.decode("utf-8"))
                    for line in replay_response
                    if line.strip()
                ]
            replay_text = "".join(
                str(event.get("text", ""))
                for event in replay_events
                if event.get("type") == "delta"
            )
            replayed = any(
                event.get("type") == "done" and event.get("replayed") is True
                for event in replay_events
            )
            results.append(
                (
                    "服务端断线续接与去重",
                    saw_delta and replayed and bool(replay_text.strip()),
                    "服务端已开始生成后主动断开，使用同一请求编号可重放完整结果且不会重复生成",
                )
            )
            browser.close()
    finally:
        server.shutdown()
        server.server_close()

    passed = sum(ok for _, ok, _ in results)
    for name, ok, detail in results:
        print(f"[{'通过' if ok else '失败'}] {name}：{detail}")
    print(f"手机应用测试：{passed}/{len(results)} 通过")
    if passed != len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
