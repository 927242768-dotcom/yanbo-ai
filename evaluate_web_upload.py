"""自动验证彦博网页端的图片按钮与 Ctrl+V 粘贴功能。"""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path

from playwright.async_api import async_playwright

from assistant_engine import DISPLAY_NAME
from console_utils import configure_utf8_console


EDGE_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]

# 1×1 PNG，用来模拟从截图工具复制到剪贴板的图片。
PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAusB9Wl2nWQAAAAASUVORK5CYII="
)


async def main_async() -> None:
    executable = next((path for path in EDGE_CANDIDATES if path.exists()), None)
    if executable is None:
        raise FileNotFoundError("没有找到浏览器程序。")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path=str(executable),
            headless=True,
        )
        page = await browser.new_page()
        await page.goto("http://127.0.0.1:7860/?test=upload", wait_until="networkidle")

        title = await page.title()
        attach = page.locator("#attach")
        button_visible = await attach.is_visible()
        button_text = (await attach.inner_text()).strip()

        async with page.expect_file_chooser() as chooser_info:
            await attach.click()
        chooser = await chooser_info.value
        await chooser.set_files(
            {
                "name": "chosen-test.png",
                "mimeType": "image/png",
                "buffer": base64.b64decode(PNG_BASE64),
            }
        )
        await page.wait_for_timeout(150)
        chooser_preview = await page.locator("#preview").is_visible()
        chooser_name = (await page.locator("#previewName").inner_text()).strip()
        await page.locator("#removeImage").click()

        await page.evaluate(
            """async (base64Png) => {
                const binary = atob(base64Png);
                const bytes = new Uint8Array(binary.length);
                for (let index = 0; index < binary.length; index += 1) {
                    bytes[index] = binary.charCodeAt(index);
                }
                const file = new File([bytes], 'pasted-test.png', {type: 'image/png'});
                const transfer = new DataTransfer();
                transfer.items.add(file);
                const event = new ClipboardEvent('paste', {
                    clipboardData: transfer,
                    bubbles: true,
                    cancelable: true,
                });
                document.dispatchEvent(event);
            }""",
            PNG_BASE64,
        )
        await page.wait_for_timeout(200)

        preview_visible = await page.locator("#preview").is_visible()
        preview_name = (await page.locator("#previewName").inner_text()).strip()
        placeholder = await page.locator("#input").get_attribute("placeholder")
        await browser.close()

    checks = {
        "页面版本": DISPLAY_NAME in title,
        "上传按钮可见": button_visible and "上传图片" in button_text,
        "点击按钮选择图片": chooser_preview and chooser_name == "chosen-test.png",
        "粘贴图片预览": preview_visible and preview_name == "pasted-test.png",
        "输入框粘贴提示": bool(placeholder and "Ctrl+V" in placeholder),
    }
    for name, passed in checks.items():
        print(f"[{'通过' if passed else '失败'}] {name}")
    if not all(checks.values()):
        raise SystemExit(1)
    print("网页图片入口与粘贴测试全部通过。")


def main() -> None:
    configure_utf8_console()
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
