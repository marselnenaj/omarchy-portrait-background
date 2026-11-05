#!/usr/bin/env python3
"""Write displays/portrait-runtime.json for a theme from its own portrait pictures.

    python3 tools/make-runtime-manifest.py <theme-folder> displays/portrait-9x16.png [displays/portrait-10x16.webp ...]

Each picture must already be in the theme's displays/ folder, a PNG, JPEG or WebP, portrait or square, at most 48 MB,
one per shape. Its size is read from its own header and its sha256 and byte count from its bytes, so the manifest is
exactly what the plugin checks. An existing manifest is not overwritten unless --force. Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import struct
import sys
from math import gcd
from pathlib import Path

MAX_BYTES = 48 * 1024 * 1024
FILE_RE = re.compile(r"^displays/[a-z0-9][a-z0-9._-]{0,80}\.(png|jpg|jpeg|webp)$")
COMMON = [(9, 16), (10, 16), (3, 4), (2, 3), (9, 21), (1, 1)]


def header_size(b: bytes) -> tuple[str, int, int] | None:
    """Format and size of a PNG, JPEG or WebP from its first bytes; None for anything else."""
    if b[:8] == b"\x89PNG\r\n\x1a\n" and b[12:16] == b"IHDR":
        w, h = struct.unpack(">II", b[16:24])
        return "png", w, h
    if b[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(b):
            if b[i] != 0xFF:
                return None
            marker = b[i + 1]
            if marker == 0xFF:
                i += 1
                continue
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            if marker in (0xD9, 0xDA):
                return None
            length = struct.unpack(">H", b[i + 2:i + 4])[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", b[i + 5:i + 9])
                return "jpeg", w, h
            i += 2 + length
        return None
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP" and len(b) >= 30:
        tag = b[12:16]
        if tag == b"VP8X":
            return "webp", int.from_bytes(b[24:27], "little") + 1, int.from_bytes(b[27:30], "little") + 1
        if tag == b"VP8L" and b[20] == 0x2F:
            bits = int.from_bytes(b[21:25], "little")
            return "webp", (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if tag == b"VP8 " and b[23:26] == b"\x9d\x01\x2a":
            return "webp", int.from_bytes(b[26:28], "little") & 0x3FFF, int.from_bytes(b[28:30], "little") & 0x3FFF
    return None


def aspect_of(w: int, h: int) -> str:
    r = w / h
    for a, b in COMMON:
        if abs(r / (a / b) - 1) < 0.01:
            return f"{a}:{b}"
    d = gcd(w, h)
    return f"{w // d}:{h // d}" if w // d <= 64 and h // d <= 64 else f"{round(r, 3)}:1"


def orientation(w: int, h: int) -> str:
    if abs(w - h) <= max(w, h) * 0.05:
        return "square"
    return "landscape" if w > h else "portrait"


def entry(theme: Path, rel: str) -> dict:
    if not FILE_RE.match(rel) or ".." in rel:
        raise SystemExit(f"{rel}: give a path like displays/portrait-9x16.png (lower case, PNG, JPEG or WebP, directly in displays/).")
    path = theme / rel
    st = os.lstat(path)
    if not stat.S_ISREG(st.st_mode) or os.path.realpath(path) != str(path.resolve(strict=True)) or path.parent.is_symlink():
        raise SystemExit(f"{rel}: not a regular file directly in the theme (links are refused by the plugin).")
    if st.st_size > MAX_BYTES:
        raise SystemExit(f"{rel}: larger than 48 MB.")
    data = path.read_bytes()
    head = header_size(data[:262144])
    if not head:
        raise SystemExit(f"{rel}: not a PNG, JPEG or WebP whose size can be read from its header.")
    fmt, w, h = head
    ext = rel.rsplit(".", 1)[1]
    if fmt != ("jpeg" if ext in ("jpg", "jpeg") else ext):
        raise SystemExit(f"{rel}: it is a {fmt} named .{ext}.")
    if not (320 <= w <= 16384 and 320 <= h <= 16384):
        raise SystemExit(f"{rel}: {w} x {h} is outside 320 to 16384 px.")
    o = orientation(w, h)
    if o == "landscape":
        raise SystemExit(f"{rel}: {w} x {h} is landscape; landscape screens use the theme's backgrounds/.")
    return {"aspect": aspect_of(w, h), "orientation": o, "width": w, "height": h, "file": rel, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "status": "artwork"}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("theme", type=Path)
    p.add_argument("pictures", nargs="+")
    p.add_argument("--slug", help="the theme's folder name (default: the folder's name)")
    p.add_argument("--force", action="store_true", help="replace an existing manifest")
    args = p.parse_args(argv)
    theme = args.theme.resolve(strict=True)
    out = theme / "displays" / "portrait-runtime.json"
    if out.exists() and not args.force:
        raise SystemExit(f"{out} exists; pass --force to replace it.")
    entries = [entry(theme, rel) for rel in args.pictures]
    if len({e["aspect"] for e in entries}) != len(entries):
        raise SystemExit("Give one picture per shape.")
    if len(entries) > 6:
        raise SystemExit("At most 6 compositions.")
    slug = args.slug or theme.name
    manifest = {"kind": "bogen-portrait-runtime", "format": 1, "theme": slug, "appliesTo": "theme-backgrounds", "wallpapers": entries, "incomplete": []}
    text = json.dumps(manifest, indent=2) + "\n"
    if len(text.encode()) > 65536:
        raise SystemExit("The manifest would be larger than 64 KB.")
    if out.is_symlink():
        raise SystemExit(f"{out} is a link; it is not written through.")
    out.write_text(text, encoding="utf-8")
    print(f"Wrote {out}: {', '.join(e['aspect'] + ' ' + e['file'] for e in entries)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
