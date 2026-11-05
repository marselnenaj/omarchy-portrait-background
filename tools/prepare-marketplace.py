#!/usr/bin/env python3
"""Generate the inspectable marketplace snapshot; end users still use the installer.

Run on the release host with its tested Omarchy version. --check writes nothing.
The snapshot is real runnable source, not a placeholder for the marketplace scanner.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "installer"))
import portrait_background as pb


def artifacts(omarchy_path: Path, omarchy_version: str) -> dict[Path, str]:
    env = pb.Env(Path.home(), omarchy_path, "omarchy", "omarchy-shell")
    files, sha = pb.build(env)
    manifest = json.loads(files["manifest.json"])
    manifest["entryPoints"] = {"service": "plugin/Background.qml"}
    # This is a review snapshot. Ownership marks belong to installer-generated copies only.
    del manifest["bogen"]
    manifest["description"] = "Theme-provided portrait wallpapers, automatically matched to each monitor's shape."
    manifest["homepage"] = "https://github.com/marselnenaj/omarchy-portrait-background"
    provenance = {
        "format": 1, "pluginVersion": pb.PLUGIN_VERSION,
        "stockFile": "shell/plugins/background/Background.qml", "stockSha256": sha,
        "testedOmarchyVersion": omarchy_version, "installation": "manual",
        "note": "Review snapshot only. Install with portrait-background to derive from the user's own Omarchy.",
    }
    return {
        ROOT / "manifest.json": json.dumps(manifest, indent=2) + "\n",
        ROOT / "plugin" / "Background.qml": files["Background.qml"],
        ROOT / "patch" / "marketplace-snapshot.json": json.dumps(provenance, indent=2) + "\n",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--omarchy-path", type=Path, default=Path("/usr/share/omarchy"))
    p.add_argument("--check", action="store_true")
    p.add_argument("--omarchy-version", help="explicit tested package version, otherwise read from omarchy version")
    args = p.parse_args()
    version = args.omarchy_version or subprocess.run(
        [pb.find_bin("omarchy", args.omarchy_path), "version"], capture_output=True, text=True, check=True, timeout=5
    ).stdout.strip()
    if not version:
        p.error("the tested Omarchy version must be recorded")
    for path, text in artifacts(args.omarchy_path, version).items():
        if args.check:
            if not path.is_file() or path.read_text() != text:
                print(f"Stale release snapshot: {path.relative_to(ROOT)}", file=sys.stderr)
                return 1
        else:
            path.write_text(text)
            print(f"Wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
