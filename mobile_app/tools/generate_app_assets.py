"""生成彦博 AI 的 Android、iOS 与 PWA 图标和启动图。"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from console_utils import configure_utf8_console

BLUE = (37, 99, 235)
PURPLE = (124, 58, 237)
WHITE = (255, 255, 255)
FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\msyhbd.ttc"),
    Path(r"C:\Windows\Fonts\msyh.ttc"),
    Path(r"C:\Windows\Fonts\simhei.ttf"),
]


def font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default(size=size)


def gradient(size: int) -> Image.Image:
    image = Image.new("RGB", (size, size))
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            ratio = (x + y) / max(1, 2 * (size - 1))
            pixels[x, y] = tuple(
                round(BLUE[index] * (1 - ratio) + PURPLE[index] * ratio)
                for index in range(3)
            )
    return image


def draw_brand(size: int, *, round_mask: bool = False) -> Image.Image:
    base = gradient(size).convert("RGBA")
    draw = ImageDraw.Draw(base)

    # 轻量电路线条，增强科技感但保持图标简洁。
    line_width = max(2, size // 120)
    for start, end in [
        ((size * 0.13, size * 0.28), (size * 0.32, size * 0.28)),
        ((size * 0.68, size * 0.72), (size * 0.87, size * 0.72)),
        ((size * 0.22, size * 0.80), (size * 0.22, size * 0.66)),
        ((size * 0.78, size * 0.20), (size * 0.78, size * 0.34)),
    ]:
        draw.line([start, end], fill=(255, 255, 255, 95), width=line_width)
        radius = max(3, size // 80)
        for point in (start, end):
            x, y = point
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(255, 255, 255, 145))

    text_font = font(round(size * 0.52))
    bbox = draw.textbbox((0, 0), "彦", font=text_font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (size - text_width) / 2 - bbox[0]
    y = (size - text_height) / 2 - bbox[1] - size * 0.015
    shadow = max(1, size // 110)
    draw.text((x + shadow, y + shadow), "彦", font=text_font, fill=(15, 23, 42, 70))
    draw.text((x, y), "彦", font=text_font, fill=WHITE)

    if round_mask:
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
        base.putalpha(mask)
    return base


def draw_foreground(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    text_font = font(round(size * 0.46))
    bbox = draw.textbbox((0, 0), "彦", font=text_font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    x = (size - width) / 2 - bbox[0]
    y = (size - height) / 2 - bbox[1]
    draw.text((x, y), "彦", font=text_font, fill=WHITE)
    return image


def save_resized(image: Image.Image, path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.resize((size, size), Image.Resampling.LANCZOS).save(path, optimize=True)


def main() -> None:
    configure_utf8_console()
    master = draw_brand(1024)
    round_master = draw_brand(1024, round_mask=True)

    # PWA 与网页图标。
    mobile = ROOT / "mobile"
    save_resized(master, mobile / "icon-192.png", 192)
    save_resized(master, mobile / "icon-512.png", 512)
    save_resized(master, mobile / "apple-touch-icon.png", 180)
    web = ROOT / "mobile_app" / "www"
    save_resized(master, web / "icon-192.png", 192)
    save_resized(master, web / "icon-512.png", 512)

    # Android 传统图标与自适应图标。自适应背景必须使用品牌色，避免桌面显示白框。
    android_res = ROOT / "mobile_app" / "android" / "app" / "src" / "main" / "res"
    background_vector = '''<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp"
    android:height="108dp"
    android:viewportWidth="108"
    android:viewportHeight="108">
    <path android:fillColor="#1D4ED8" android:pathData="M0,0h108v108h-108z"/>
    <path android:fillColor="#7C3AED" android:fillAlpha="0.72" android:pathData="M108,0L108,108L42,108Z"/>
    <path android:fillColor="#FFFFFF" android:fillAlpha="0.12" android:pathData="M-12,76C20,42 52,24 120,20L120,42C58,46 25,60 -12,96Z"/>
</vector>
'''
    background_path = android_res / "drawable" / "ic_launcher_background.xml"
    background_path.parent.mkdir(parents=True, exist_ok=True)
    background_path.write_text(background_vector, encoding="utf-8")
    adaptive_icon = '''<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@drawable/ic_launcher_background"/>
    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>
</adaptive-icon>
'''
    adaptive_dir = android_res / "mipmap-anydpi-v26"
    adaptive_dir.mkdir(parents=True, exist_ok=True)
    (adaptive_dir / "ic_launcher.xml").write_text(adaptive_icon, encoding="utf-8")
    (adaptive_dir / "ic_launcher_round.xml").write_text(adaptive_icon, encoding="utf-8")
    color_path = android_res / "values" / "ic_launcher_background.xml"
    color_path.parent.mkdir(parents=True, exist_ok=True)
    color_path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<resources><color name="ic_launcher_background">#1D4ED8</color></resources>\n',
        encoding="utf-8",
    )
    densities = {
        "mipmap-mdpi": (48, 108),
        "mipmap-hdpi": (72, 162),
        "mipmap-xhdpi": (96, 216),
        "mipmap-xxhdpi": (144, 324),
        "mipmap-xxxhdpi": (192, 432),
    }
    for folder, (legacy_size, foreground_size) in densities.items():
        target = android_res / folder
        save_resized(master, target / "ic_launcher.png", legacy_size)
        save_resized(round_master, target / "ic_launcher_round.png", legacy_size)
        foreground = draw_foreground(foreground_size)
        target.mkdir(parents=True, exist_ok=True)
        foreground.save(target / "ic_launcher_foreground.png", optimize=True)

    # iOS App Store 图标。
    ios_assets = ROOT / "mobile_app" / "ios" / "App" / "App" / "Assets.xcassets"
    save_resized(master, ios_assets / "AppIcon.appiconset" / "AppIcon-512@2x.png", 1024)

    # iOS 启动图。
    splash = gradient(2732).convert("RGBA")
    splash.alpha_composite(draw_brand(720).resize((720, 720)), ((2732 - 720) // 2, (2732 - 720) // 2))
    splash_dir = ios_assets / "Splash.imageset"
    for filename in ("splash-2732x2732.png", "splash-2732x2732-1.png", "splash-2732x2732-2.png"):
        splash.save(splash_dir / filename, optimize=True)

    print("彦博 AI 图标与启动图已生成。")


if __name__ == "__main__":
    main()
