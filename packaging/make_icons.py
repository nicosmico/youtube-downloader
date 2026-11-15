"""Generates the app icon (a download arrow on a rounded square): PNG, .ico and (on macOS) .icns.

    uv run --with pillow python packaging/make_icons.py

Original artwork drawn with Pillow; no third-party imagery. The outputs are committed under
packaging/assets/, so the CI builds do not need to run this.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent / "assets"
SIZE = 1024
SCALE = 2  # supersampling for smooth edges


def draw_master() -> Image.Image:
    s = SIZE * SCALE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    margin = int(s * 0.06)
    d.rounded_rectangle((margin, margin, s - margin, s - margin), radius=int(s * 0.22), fill=(37, 99, 235, 255))
    white = (255, 255, 255, 255)
    cx = s // 2
    # shaft + head of the arrow
    d.rounded_rectangle((cx - s * 0.06, s * 0.20, cx + s * 0.06, s * 0.52), radius=int(s * 0.03), fill=white)
    d.polygon([(cx - s * 0.20, s * 0.46), (cx + s * 0.20, s * 0.46), (cx, s * 0.68)], fill=white)
    # tray
    d.rounded_rectangle((s * 0.24, s * 0.74, s * 0.76, s * 0.80), radius=int(s * 0.03), fill=white)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def main() -> None:
    master = draw_master()
    master.save(ASSETS / "icon.png")
    master.save(ASSETS / "icon.ico", sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
    if sys.platform == "darwin":
        with tempfile.TemporaryDirectory() as tmp:
            iconset = Path(tmp) / "icon.iconset"
            iconset.mkdir()
            for base in (16, 32, 128, 256, 512):
                master.resize((base, base), Image.LANCZOS).save(iconset / f"icon_{base}x{base}.png")
                master.resize((base * 2, base * 2), Image.LANCZOS).save(iconset / f"icon_{base}x{base}@2x.png")
            subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(ASSETS / "icon.icns")], check=True)


if __name__ == "__main__":
    main()
