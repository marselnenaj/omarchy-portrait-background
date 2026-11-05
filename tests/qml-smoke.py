#!/usr/bin/env python3
"""Exercise PortraitMapping in a separate Quickshell process with no windows or user-config writes.

Needs Quickshell, Qt 6 and a working Wayland session. Uses a synthetic theme and a temporary cache.
This checks QML loading, subprocess integration and screen selection, not pixel rendering.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    with tempfile.TemporaryDirectory(prefix="portrait-qml-smoke-") as folder:
        root = Path(folder)
        theme = root / "theme"
        subprocess.run([sys.executable, str(ROOT / "examples/make-example-theme.py"), str(theme)], check=True, capture_output=True)
        mapping = (ROOT / "plugin/PortraitMapping.qml").read_text()
        mapping = mapping.replace('home + "/.local/state/omarchy/current/theme"', json.dumps(str(theme)))
        (root / "PortraitMapping.qml").write_text(mapping)
        shutil.copyfile(ROOT / "plugin/PortraitRuntime.js", root / "PortraitRuntime.js")
        (root / "shell.qml").write_text('''import QtQuick
import Quickshell
ShellRoot {
  Item {
    id: host
    property string incomingBackground: ""
    property string currentBackground: THE_BACKGROUND
    property string displayedBackground: currentBackground
    property real revealProgress: 1
    property var portraitIncomingMap: null
    property var portraitDisplayedMap: null
    property var portraitOldMap: null
    property bool finishingTransition: false
    PortraitMapping {
      id: mapping
      host: host
      Component.onCompleted: Qt.callLater(resolve)
      onMapStateChanged: {
        if (["active", "invalid", "error"].indexOf(mapState) >= 0)
          Qt.callLater(function() { console.log("PORTRAIT_SMOKE " + status()); Qt.quit() })
      }
    }
  }
  Timer { interval: 15000; running: true; onTriggered: Qt.quit() }
}
'''.replace("THE_BACKGROUND", json.dumps(str(theme / "backgrounds/example.png"))))
        env = dict(os.environ)
        if "XDG_RUNTIME_DIR" in env:
            env["WAYLAND_DISPLAY"] = str(Path(env["XDG_RUNTIME_DIR"]) / env.get("WAYLAND_DISPLAY", "wayland-0"))
        (root / "runtime").mkdir(mode=0o700)
        env["XDG_RUNTIME_DIR"] = str(root / "runtime")
        env["XDG_CACHE_HOME"] = str(root / "cache")
        env["GSETTINGS_BACKEND"] = "memory"
        result = subprocess.run(["quickshell", "--path", str(root), "--no-color"], capture_output=True, text=True, env=env, timeout=20)
        lines = (result.stdout + result.stderr).splitlines()
        reports = [json.loads(line.split("PORTRAIT_SMOKE ", 1)[1]) for line in lines if "PORTRAIT_SMOKE " in line]
        if result.returncode or not reports:
            print("\n".join(lines), file=sys.stderr)
            raise SystemExit("Quickshell did not produce a successful runtime report")
        report = reports[-1]
        assert report["state"] == "active", report
        assert len(report["compositions"]) == 1, report
        for screen in report["screens"]:
            if screen["orientation"] == "landscape":
                assert screen["shows"] == "global background", screen
            elif abs((screen["width"] / screen["height"]) / (9 / 16) - 1) <= 0.015:
                assert screen["shows"] == "portrait 9:16", screen
        print(json.dumps({"version": report["version"], "state": report["state"], "screens": report["screens"]}, indent=2))


if __name__ == "__main__":
    main()
