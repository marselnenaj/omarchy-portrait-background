"""A made-up home and Omarchy for the installer tests: nothing here touches the real home or runs a real command."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "installer"))

import portrait_background as pb  # noqa: E402

FIXTURE = (ROOT / "tests" / "fixtures" / "background-stock-anchors.qml").read_text(encoding="utf-8")

# Stand-ins for `omarchy` and `omarchy-shell`. They log their arguments and do to the made-up shell.json what
# Omarchy's plugin registry does on enable and disable (shell/services/PluginRegistry.qml), nothing more.
OMARCHY_STUB = r'''#!/usr/bin/env python3
import json, sys
LOG, SHELL = {log!r}, {shell!r}
args = sys.argv[1:]
open(LOG, "a").write("omarchy " + " ".join(args) + "\n")
if args[:2] == ["plugin", "validate"]:
    sys.exit({validate_exit})
if args[:1] != ["plugin"] or len(args) != 3:
    sys.exit(2)
verb, pid = args[1], args[2]
c = json.load(open(SHELL))
c.setdefault("plugins", []); c.setdefault("disabledPlugins", [])
if verb == "enable":
    if not any(p.get("id") == pid for p in c["plugins"]):
        c["plugins"].append({{"id": pid}})
    if "omarchy.background" not in c["disabledPlugins"]:
        c["disabledPlugins"].append("omarchy.background")
        c["cloneSourceRestores"] = c.get("cloneSourceRestores", []) + [pid]
elif verb == "disable":
    c["plugins"] = [p for p in c["plugins"] if p.get("id") != pid]
    if pid in c.get("cloneSourceRestores", []):
        c["disabledPlugins"] = [d for d in c["disabledPlugins"] if d != "omarchy.background"]
        c["cloneSourceRestores"] = [r for r in c["cloneSourceRestores"] if r != pid]
else:
    sys.exit(2)
json.dump(c, open(SHELL, "w"), indent=2)
print(verb)
'''

SHELL_STUB = r'''#!/usr/bin/env python3
import sys
open({log!r}, "a").write("omarchy-shell " + " ".join(sys.argv[1:]) + "\n")
print("ok")
'''


class FakeHost:
    def __init__(self, stock: str = FIXTURE, validate_exit: int = 0):
        self.tmp = tempfile.TemporaryDirectory(prefix="portrait-bg-")
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.omarchy = self.root / "omarchy"
        self.log = self.root / "calls.log"
        (self.home / ".config" / "omarchy" / "plugins").mkdir(parents=True)
        # Someone else's plugin, which must stay as it is.
        weather = self.home / ".config" / "omarchy" / "plugins" / "someone.weather"
        weather.mkdir()
        (weather / "manifest.json").write_text(json.dumps({"id": "someone.weather", "omarchy": {"clonedFrom": "omarchy.weather"}}))
        self.write_shell({"plugins": [{"id": "someone.weather"}], "disabledPlugins": ["omarchy.weather"]})
        self.write_stock(stock)
        bins = self.root / "bin"
        bins.mkdir()
        self.omarchy_bin = bins / "omarchy"
        self.shell_bin = bins / "omarchy-shell"
        self.omarchy_bin.write_text(OMARCHY_STUB.format(log=str(self.log), shell=str(self.shell_json), validate_exit=validate_exit))
        self.shell_bin.write_text(SHELL_STUB.format(log=str(self.log)))
        os.chmod(self.omarchy_bin, 0o755)
        os.chmod(self.shell_bin, 0o755)
        self.env = pb.Env(self.home, self.omarchy, str(self.omarchy_bin), str(self.shell_bin))

    @property
    def shell_json(self) -> Path:
        return self.home / ".config" / "omarchy" / "shell.json"

    def write_shell(self, data: dict) -> None:
        self.shell_json.write_text(json.dumps(data, indent=2))

    def shell(self) -> dict:
        return json.loads(self.shell_json.read_text())

    def write_stock(self, text: str) -> None:
        d = self.omarchy / "shell" / "plugins" / "background"
        d.mkdir(parents=True, exist_ok=True)
        (d / "Background.qml").write_text(text)
        (d / "manifest.json").write_text(json.dumps({"schemaVersion": 1, "id": "omarchy.background", "name": "Background", "version": "1.0.0", "kinds": ["service"], "entryPoints": {"service": "Background.qml"}}))

    def calls(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []

    def close(self) -> None:
        self.tmp.cleanup()
