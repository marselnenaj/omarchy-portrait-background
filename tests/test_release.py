"""Release metadata, real runtime scripts and malformed theme-author inputs."""

import ast
import importlib.util
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, pb

spec = importlib.util.spec_from_file_location("make_manifest", ROOT / "tools/make-runtime-manifest.py")
author = importlib.util.module_from_spec(spec)
spec.loader.exec_module(author)


def script(name):
    source = (ROOT / "plugin/PortraitMapping.qml").read_text()
    block = re.search(r"readonly property string " + name + r": \[(.*?)\n  \]", source, re.S)[1]
    return "\n".join(ast.literal_eval(line.strip().removesuffix(",")) for line in block.strip().splitlines())


class ReleaseTest(unittest.TestCase):
    def test_review_snapshot_reproduces_its_recorded_source_hash(self):
        snapshot = (ROOT / "plugin/Background.qml").read_text()
        stock = snapshot.split("\n", 4)[4]
        for anchor in reversed(pb.SPEC["anchors"]):
            self.assertEqual(stock.count(anchor["replace"]), 1, anchor["name"])
            stock = stock.replace(anchor["replace"], anchor["find"], 1)
        provenance = json.loads((ROOT / "patch/marketplace-snapshot.json").read_text())
        self.assertEqual(pb.sha256_text(stock), provenance["stockSha256"])
        self.assertEqual(pb.patch_background(stock).source, snapshot)

    def test_root_manifest_points_to_real_versioned_runtime(self):
        manifest = json.loads((ROOT / "manifest.json").read_text())
        self.assertEqual(manifest["id"], pb.PLUGIN_ID)
        self.assertEqual(manifest["version"], pb.PLUGIN_VERSION)
        self.assertEqual(manifest["license"], "MIT")
        for entry in manifest["entryPoints"].values():
            self.assertTrue((ROOT / entry).is_file())
        self.assertIn("PortraitMapping {", (ROOT / manifest["entryPoints"]["service"]).read_text())

    def test_truncated_png_and_nonadvancing_jpeg_are_rejected(self):
        self.assertIsNone(author.header_size(b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR"))
        self.assertIsNone(author.header_size(b"\xff\xd8\xff\xe0\0\0" + b"\0" * 32))

    def test_runtime_scripts_hash_copies_and_refuse_links_and_changed_artwork(self):
        with tempfile.TemporaryDirectory(prefix="portrait-release-") as directory:
            root = Path(directory)
            theme = root / "theme with spaces; $(touch nope)"
            subprocess.run(["python3", str(ROOT / "examples/make-example-theme.py"), str(theme)], check=True, capture_output=True)
            manifest = json.loads((theme / "displays/portrait-runtime.json").read_text())
            entry = manifest["wallpapers"][0]
            cache = root / "cache"
            def run_asset():
                return subprocess.run(["timeout", "10s", "bash", "-c", script("assetScript"), "test", str(theme), entry["file"], str(cache), entry["sha256"], str(entry["bytes"]), "png"], check=True, capture_output=True, text=True).stdout
            output = run_asset()
            self.assertIn("path " + str(cache), output)
            self.assertIn("header ", output)
            self.assertFalse((root / "nope").exists())
            image = theme / entry["file"]
            image.write_bytes(image.read_bytes() + b"changed")
            for cached in cache.iterdir():
                cached.unlink()
            self.assertIn("status sha", run_asset())
            image.unlink()
            image.symlink_to(ROOT / "LICENSE")
            self.assertIn("status link", run_asset())

    def test_theme_resolver_and_cache_pruner_use_literal_arguments(self):
        with tempfile.TemporaryDirectory(prefix="portrait-release-") as directory:
            root = Path(directory)
            theme = root / "theme"
            subprocess.run(["python3", str(ROOT / "examples/make-example-theme.py"), str(theme)], check=True, capture_output=True)
            command = ["bash", "-c", script("resolveScript"), "test", str(theme)]
            self.assertIn("\nmanifest\n", subprocess.run(command, capture_output=True, text=True, check=True).stdout)
            manifest = theme / "displays/portrait-runtime.json"
            manifest.unlink()
            self.assertIn("status no-manifest", subprocess.run(command, capture_output=True, text=True, check=True).stdout)
            manifest.symlink_to(ROOT / "LICENSE")
            self.assertIn("status link", subprocess.run(command, capture_output=True, text=True, check=True).stdout)
            cache = root / "cache"
            cache.mkdir()
            (cache / "keep").write_text("keep")
            (cache / "unused").write_text("unused")
            (cache / "link").symlink_to(ROOT / "LICENSE")
            subprocess.run(["bash", "-c", script("pruneScript"), "test", str(cache), "keep"], check=True)
            self.assertTrue((cache / "keep").exists())
            self.assertFalse((cache / "unused").exists())
            self.assertTrue((cache / "link").is_symlink())
