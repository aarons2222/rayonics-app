#!/usr/bin/env python3
"""Generate app icons for macOS (.icns) and Windows (.ico)."""

from PIL import Image, ImageDraw, ImageFont
import struct
from pathlib import Path
from io import BytesIO

OUT = Path(__file__).parent / "assets"
OUT.mkdir(exist_ok=True)


def draw_icon(size=512):
    """Draw a professional key reader icon."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = size // 8
    # Background rounded rect
    bg_box = [pad, pad, size - pad, size - pad]
    draw.rounded_rectangle(bg_box, radius=size // 6, fill="#1a1d27", outline="#2a2d3a", width=3)

    cx, cy = size // 2, size // 2 - size // 16

    # Key head (circle with hole)
    head_r = size // 6
    draw.ellipse(
        [cx - head_r, cy - head_r, cx + head_r, cy + head_r],
        outline="#3ecf8e", width=max(size // 40, 4)
    )
    inner_r = head_r // 3
    draw.ellipse(
        [cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r],
        fill="#1a1d27"
    )

    # Key shaft
    shaft_w = size // 30
    shaft_top = cy + head_r - shaft_w
    shaft_bottom = cy + head_r + size // 4
    draw.rectangle(
        [cx - shaft_w, shaft_top, cx + shaft_w, shaft_bottom],
        fill="#3ecf8e"
    )

    # Key teeth
    tooth_w = size // 10
    tooth_h = size // 24
    for i, offset in enumerate([0, tooth_h * 3]):
        y = shaft_bottom - tooth_h - offset
        draw.rectangle(
            [cx + shaft_w, y, cx + shaft_w + tooth_w, y + tooth_h],
            fill="#3ecf8e"
        )

    # BLE signal arcs (top right)
    arc_cx = cx + head_r + size // 10
    arc_cy = cy - head_r + size // 10
    for i, r in enumerate([size // 12, size // 8, size // 6]):
        alpha = 255 - i * 60
        draw.arc(
            [arc_cx - r, arc_cy - r, arc_cx + r, arc_cy + r],
            start=-60, end=60, fill=(94, 141, 239, alpha), width=max(size // 80, 2)
        )

    return img


def save_ico(img, path):
    """Save as .ico with multiple sizes."""
    sizes = [16, 32, 48, 64, 128, 256]
    imgs = [img.resize((s, s), Image.LANCZOS) for s in sizes]
    imgs[0].save(path, format="ICO", sizes=[(s, s) for s in sizes], append_images=imgs[1:])


def save_icns_png(img, path):
    """Save high-res PNG for macOS (PyInstaller uses this)."""
    img.save(path, format="PNG")


if __name__ == "__main__":
    icon = draw_icon(512)

    # Windows .ico
    save_ico(icon, OUT / "icon.ico")
    print(f"Created {OUT / 'icon.ico'}")

    # macOS icon (PNG, PyInstaller converts)
    save_icns_png(icon, OUT / "icon.png")
    print(f"Created {OUT / 'icon.png'}")

    # Menu bar icon (small, template)
    menu = draw_icon(44)
    menu.save(OUT / "menubar.png")
    print(f"Created {OUT / 'menubar.png'}")

    print("Done")
