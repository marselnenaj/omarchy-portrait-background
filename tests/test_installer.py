"""The installer in a made-up home with stand-ins for omarchy and omarchy-shell: plan, apply, refuse, back up, roll back."""

import hashlib
import json
import os
import unittest
from pathlib import Path

from helpers import FIXTURE, ROOT, FakeHost, pb


class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.host = FakeHost()
        self.env = self.host.env
        self.target = self.env.target

    def tearDown(self):
        self.host.close()

    # ------------------------------------------------------------ plan and apply

    def test_plans_without_changing_anything(self):
        plan = pb.install(self.env)
        self.assertTrue(plan.possible)
        self.assertFalse(plan.applied)
        self.assertFalse(self.target.exists())
        self.assertFalse(self.env.state_dir.exists())
        self.assertEqual(self.host.calls(), [])
        self.assertEqual(pb.status(self.env)["state"], "not-installed")

    def test_installs_a_clone_of_the_background_plugin_and_enables_it_only_on_request(self):
        plan = pb.install(self.env, apply=True)
        self.assertTrue(plan.applied, plan.blockers)
        m = json.loads((self.target / "manifest.json").read_text())
        self.assertEqual(m["id"], "bogen.portrait-background")
        self.assertEqual(m["omarchy"], {"clonedFrom": "omarchy.background"})
        self.assertEqual(m["entryPoints"], {"service": "Background.qml"})
        self.assertEqual(m["bogen"]["plugin"], "portrait-background")
        self.assertEqual(m["bogen"]["installer"], "omarchy-portrait-background")
        self.assertEqual(m["version"], pb.PLUGIN_VERSION)
        for name in ("PortraitMapping.qml", "PortraitRuntime.js"):
            self.assertEqual((self.target / name).read_bytes(), (ROOT / "plugin" / name).read_bytes())
        for name, digest in m["bogen"]["files"].items():
            self.assertEqual(hashlib.sha256((self.target / name).read_bytes()).hexdigest(), digest, name)
        self.assertIn("PortraitMapping { id: portraitMapping; host: root }", (self.target / "Background.qml").read_text())
        # Staged folder validated with Omarchy's own validator; nothing enabled.
        self.assertEqual(len(self.host.calls()), 1)
        self.assertTrue(self.host.calls()[0].startswith("omarchy plugin validate "))
        self.assertEqual(pb.status(self.env)["state"], "installed")
        self.assertEqual(oct(self.env.state_dir.stat().st_mode & 0o777), "0o700")

        enable = pb.enable(self.env)
        self.assertEqual(enable.commands, [[self.env.shell_bin, "shell", "rescanPlugins"], [self.env.omarchy_bin, "plugin", "enable", pb.PLUGIN_ID]])
        self.assertEqual(len(self.host.calls()), 1)
        self.assertTrue(pb.enable(self.env, apply=True).applied)
        self.assertEqual(self.host.calls()[1:], ["omarchy-shell shell rescanPlugins", f"omarchy plugin enable {pb.PLUGIN_ID}"])
        self.assertEqual([p["id"] for p in self.host.shell()["plugins"]], ["someone.weather", pb.PLUGIN_ID])
        self.assertEqual(self.host.shell()["disabledPlugins"], ["omarchy.weather", "omarchy.background"])
        self.assertEqual(pb.status(self.env)["state"], "enabled")

        self.assertTrue(pb.disable(self.env, apply=True).applied)
        self.assertEqual(self.host.shell()["plugins"], [{"id": "someone.weather"}])
        self.assertEqual(self.host.shell()["disabledPlugins"], ["omarchy.weather"])
        self.assertTrue((self.env.plugins_dir / "someone.weather" / "manifest.json").is_file())

    def test_a_failed_validation_writes_nothing(self):
        self.host.close()
        self.host = FakeHost(validate_exit=1)
        self.env = self.host.env
        with self.assertRaises(pb.Refused):
            pb.install(self.env, apply=True)
        self.assertFalse(self.env.target.exists())
        self.assertEqual([n for n in os.listdir(self.env.plugins_dir) if n.startswith(".")], [])

    def test_up_to_date_is_left_alone(self):
        pb.install(self.env, apply=True)
        again = pb.install(self.env, apply=True)
        self.assertFalse(again.applied)
        self.assertIn("Nothing to do", again.steps[0])

    # ------------------------------------------------------------ refusals

    def test_never_writes_over_a_folder_that_is_not_this_plugin(self):
        self.target.mkdir()
        (self.target / "manifest.json").write_text(json.dumps({"id": pb.PLUGIN_ID, "name": "Mine"}))
        plan = pb.install(self.env, apply=True, force=True)
        self.assertFalse(plan.applied)
        self.assertIn("not this plugin", plan.blockers[0])
        self.assertEqual(json.loads((self.target / "manifest.json").read_text())["name"], "Mine")

    def test_never_writes_through_a_link(self):
        elsewhere = self.host.root / "elsewhere"
        elsewhere.mkdir()
        self.target.symlink_to(elsewhere)
        plan = pb.install(self.env, apply=True, force=True)
        self.assertFalse(plan.applied)
        self.assertEqual(os.listdir(elsewhere), [])
        os.unlink(self.target)
        # A leftover staging path that is a link is removed as a link, never followed.
        staging = self.env.plugins_dir / f".{pb.PLUGIN_ID}.bogen-new"
        staging.symlink_to(elsewhere)
        self.assertTrue(pb.install(self.env, apply=True).applied)
        self.assertEqual(os.listdir(elsewhere), [])
        # A state folder that is a link is refused before anything is written there.
        pb.disable(self.env, apply=True)
        state = self.env.state_dir
        for p in sorted(state.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
        state.rmdir()
        state.symlink_to(elsewhere)
        (self.target / "Background.qml").write_text("// edited\n")
        with self.assertRaises(pb.Refused):
            pb.install(self.env, apply=True, force=True)
        self.assertEqual(os.listdir(elsewhere), [])

    def test_follows_the_persons_own_link_for_local_state_but_nothing_below_it(self):
        # ~/.local/state on another drive: allowed, as Omarchy itself writes there.
        drive = self.host.root / "drive-state"
        drive.mkdir()
        (self.env.home / ".local").mkdir()
        (self.env.home / ".local" / "state").symlink_to(drive)
        pb.install(self.env, apply=True)
        self.assertTrue((drive / "bogen" / "portrait-background" / "install.json").is_file())

    def test_keeps_hand_edits_unless_forced_backs_up_and_rolls_back(self):
        pb.install(self.env, apply=True)
        qml = self.target / "Background.qml"
        qml.write_text(qml.read_text() + "\n// mine\n")
        self.assertEqual(pb.status(self.env)["installed"]["modified"], ["Background.qml"])
        refused = pb.install(self.env, apply=True)
        self.assertFalse(refused.applied)
        self.assertIn("You edited Background.qml", refused.blockers[0])
        forced = pb.install(self.env, apply=True, force=True)
        self.assertTrue(forced.applied)
        self.assertIn("// mine", (Path(forced.backup) / "Background.qml").read_text())
        self.assertNotIn("// mine", qml.read_text())
        back = pb.rollback(self.env, apply=True)
        self.assertTrue(back.applied, back.blockers)
        self.assertIn("// mine", qml.read_text())
        self.assertNotIn("// mine", (Path(back.backup) / "Background.qml").read_text())

    def test_refuses_to_derive_from_a_stock_file_it_does_not_know_and_reports_outdated_after_an_update(self):
        self.host.write_stock('Item { ShellIpc { target: "background" } }')
        plan = pb.install(self.env, apply=True)
        self.assertFalse(plan.applied)
        self.assertIn("changed where the patch goes", plan.blockers[0])
        self.assertFalse(pb.status(self.env)["stock"]["compatible"])
        self.host.write_stock(FIXTURE)
        pb.install(self.env, apply=True)
        self.assertFalse(pb.status(self.env)["installed"]["outdated"])
        self.host.write_stock(FIXTURE.replace("Item {", "Item { // updated", 1))
        self.assertTrue(pb.status(self.env)["installed"]["outdated"])
        again = pb.install(self.env, apply=True)
        self.assertTrue(again.applied)
        self.assertTrue(again.backup)
        self.assertFalse(pb.status(self.env)["installed"]["outdated"])

    def test_does_not_enable_beside_another_background_clone_or_over_a_disabled_stock_background(self):
        pb.install(self.env, apply=True)
        theirs = self.env.plugins_dir / "someone.background"
        theirs.mkdir()
        (theirs / "manifest.json").write_text(json.dumps({"id": "someone.background", "omarchy": {"clonedFrom": "omarchy.background"}}))
        plan = pb.enable(self.env, apply=True)
        self.assertFalse(plan.applied)
        self.assertIn("someone.background", plan.blockers[0])
        for p in theirs.iterdir():
            p.unlink()
        theirs.rmdir()
        self.host.write_shell({"plugins": [], "disabledPlugins": ["omarchy.background"]})
        plan = pb.enable(self.env, apply=True)
        self.assertFalse(plan.applied)
        self.assertIn("omarchy.background is disabled", plan.blockers[0])
        self.assertEqual([c for c in self.host.calls() if "enable" in c], [])

    def test_removes_its_files_only_when_disabled(self):
        pb.install(self.env, apply=True)
        pb.enable(self.env, apply=True)
        plan = pb.remove(self.env, apply=True)
        self.assertFalse(plan.applied)
        self.assertIn("Disable it first", plan.blockers[0])
        self.assertTrue(self.target.exists())
        pb.disable(self.env, apply=True)
        gone = pb.remove(self.env, apply=True)
        self.assertTrue(gone.applied)
        self.assertFalse(self.target.exists())
        self.assertTrue((Path(gone.backup) / "manifest.json").is_file())
        self.assertEqual(self.host.shell()["disabledPlugins"], ["omarchy.weather"])

    # ------------------------------------------------------------ living beside Bogen's own installer

    def test_takes_over_an_install_bogen_made_with_a_backup(self):
        # What Bogen 1.0.0 wrote: the same id and ownership mark, no installer field, an older version.
        pb.install(self.env, apply=True)
        m = json.loads((self.target / "manifest.json").read_text())
        m["version"] = "1.0.0"
        m["name"] = "Bogen portrait background"
        del m["bogen"]["installer"]
        (self.target / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
        st = pb.status(self.env)["installed"]
        self.assertTrue(st["ours"])
        self.assertEqual(st["installer"], "bogen")
        self.assertTrue(st["outdated"] or pb.PLUGIN_VERSION == "1.0.0")
        plan = pb.install(self.env, apply=True)
        if pb.PLUGIN_VERSION != "1.0.0":
            self.assertTrue(plan.applied)
            self.assertEqual(json.loads((Path(plan.backup) / "manifest.json").read_text())["version"], "1.0.0")
        self.assertTrue(pb.status(self.env)["installed"]["ours"])
        # Backups use Bogen's names and folder, so either installer can roll back the other's.
        for name in pb.status(self.env)["backups"]:
            self.assertRegex(name, pb.BACKUP_NAME)


class StaleRuntimeTest(unittest.TestCase):
    def test_says_to_restart_the_shell_only_when_the_running_version_differs(self):
        self.assertRegex(pb.stale_runtime("1.0.2", {"version": "1"}), r"still has plugin 1, and 1\.0\.2 is installed.*omarchy restart shell")
        self.assertIsNone(pb.stale_runtime("1.0.2", {"version": "1.0.2"}))
        self.assertIsNone(pb.stale_runtime(None, {"version": "1"}))
        self.assertIsNone(pb.stale_runtime("1.0.2", None))
        self.assertIsNone(pb.stale_runtime("1.0.2", {"state": "active"}))


if __name__ == "__main__":
    unittest.main()
