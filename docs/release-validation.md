# Release validation — 1.0.3

Checked on 5 November 2026, on Omarchy 4.5.0-3.

| Check | Result |
| --- | --- |
| Python installer, patch, source-snapshot and file-script tests | 26 passed |
| Shipped JavaScript runtime tests | 8 passed |
| Shell entry point syntax and help | Passed |
| `omarchy plugin validate .` | Passed |
| `tools/prepare-marketplace.py --check` | Passed against the installed stock renderer |
| Qt 6 QML parsing of generated Background.qml | Passed |
| Marketplace's manifest validator and preview optimizer | Passed locally |
| Separate Quickshell runtime process, version 1.0.3 | Loaded and verified a portrait map; chose normal landscape and 9:16 portrait backgrounds |

The separate Quickshell check uses no wallpaper windows and writes only into a temporary directory.
Run `python3 tests/qml-smoke.py` in a Wayland session to reproduce it with a synthetic theme.
It checks integration and screen selection, not rendering pixels. The pre-existing installed 1.0.2
runtime was separately observed reporting the correct choices on the actual 4K landscape and
rotated 4K portrait desktop. The release preparation did not replace that running installation.

The stock renderer's SHA-256 and the tested package version are recorded in
`patch/marketplace-snapshot.json`. CI checks that the committed generated snapshot reproduces its
recorded source hash and patch result without needing Omarchy installed.

Live hotplug, rotation changes, fractional rescaling and lock-screen behavior are not qualified.
Video and intro behavior are inherited from the stock renderer; no new end-to-end video playback
test was performed for this release. The lock screen remains separate.

The marketplace baseline requires a maintainer decision for the manual install path, even when
there are no blocking findings. Local preflight is not marketplace verification or a security audit.
The store reruns its own checks against the submitted commit. Publication requires its maintainer.

The README was checked for relative links and structure. The illustrated preview was inspected and
successfully processed by the marketplace's own optimizer. A browser rendering review was unavailable
because the connected browser host could not be reached.
