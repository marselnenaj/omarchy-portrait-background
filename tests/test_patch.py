"""Deriving Background.qml from the stock file: exact anchors, refused when they do not fit, never twice."""

import json
import re
import unittest
from pathlib import Path

from helpers import FIXTURE, ROOT, pb

STOCK = Path("/usr/share/omarchy/shell/plugins/background/Background.qml")


class PatchTest(unittest.TestCase):
    def test_spec_is_data_only_and_matches_the_plugin(self):
        spec = json.loads((ROOT / "patch" / "background-patch.json").read_text())
        self.assertEqual(spec["format"], 1)
        self.assertEqual(spec["plugin"], "portrait-background")
        self.assertEqual(spec["marker"], "// bogen.portrait-background")
        self.assertEqual(len(spec["anchors"]), 11)
        for a in spec["anchors"]:
            self.assertEqual(set(a), {"name", "find", "replace"})
            self.assertTrue(a["find"].endswith("\n") and a["replace"].endswith("\n"), a["name"])
        # The version the plugin reports at runtime is the one the installer records.
        self.assertIn(f'readonly property string pluginVersion: "{spec["pluginVersion"]}"', (ROOT / "plugin" / "PortraitMapping.qml").read_text())

    def test_patches_every_anchor_once_and_marks_it(self):
        out = pb.patch_background(FIXTURE)
        self.assertTrue(out.ok, out.reason)
        for a in pb.SPEC["anchors"]:
            self.assertIn(a["replace"], out.source, a["name"])
        self.assertRegex(out.source, r"sha256 [0-9a-f]{64}")
        self.assertEqual(out.source.count("bogen.portrait-background"), len(re.findall(r"bogen\.portrait-background", "".join(a["replace"] for a in pb.SPEC["anchors"]))) + 1)
        for kept in ['target: "background"', "MouseArea {", "root.recoverBackground(path)"]:
            self.assertIn(kept, out.source)

    def test_refuses_an_already_patched_file(self):
        out = pb.patch_background(pb.patch_background(FIXTURE).source)
        self.assertFalse(out.ok)
        self.assertIn("already patched", out.reason)

    def test_refuses_a_changed_stock_file_and_names_the_anchor(self):
        changed = FIXTURE.replace("        path: root.displayedBackground\n", "        path: root.shownBackground\n")
        out = pb.patch_background(changed)
        self.assertFalse(out.ok)
        self.assertEqual(out.missing, ["displayed frame"])
        twice = FIXTURE + FIXTURE[FIXTURE.index("  property real revealProgress"):]
        self.assertFalse(pb.patch_background(twice).ok)
        self.assertIn("not Omarchy's background plugin", pb.patch_background("Item {}").reason)

    @unittest.skipUnless(STOCK.is_file(), "no Omarchy on this machine")
    def test_patches_the_stock_file_installed_here(self):
        out = pb.patch_background(STOCK.read_text())
        self.assertTrue(out.ok, out.reason)


if __name__ == "__main__":
    unittest.main()
