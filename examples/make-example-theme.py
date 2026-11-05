#!/usr/bin/env python3
"""Make a tiny synthetic theme folder that shows the data contract: one 1080 x 1920 portrait picture drawn in code
(no photo, nothing copyrighted) and the displays/portrait-runtime.json that lists it.

    python3 examples/make-example-theme.py /tmp/example-theme

It is only an example of the files; to use a portrait picture with a real Omarchy theme, put the picture in that
theme's displays/ folder and run tools/make-runtime-manifest.py on it.
"""

import struct
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def png(width: int, height: int) -> bytes:
    """A dark field with an accent band a third of the way down: RGB, 8 bits, no dependencies."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    rows = []
    for y in range(height):
        band = height // 3 <= y < height // 3 + height // 24
        rgb = bytes((198, 255, 0)) if band else bytes((14, 14, 16))
        rows.append(b"\x00" + rgb * width)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b"")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    theme = Path(sys.argv[1])
    (theme / "displays").mkdir(parents=True, exist_ok=False)
    (theme / "displays" / "portrait-9x16.png").write_bytes(png(1080, 1920))
    return subprocess.call([sys.executable, "-I", str(ROOT / "tools" / "make-runtime-manifest.py"), str(theme), "displays/portrait-9x16.png", "--slug", "example"])


if __name__ == "__main__":
    sys.exit(main())
