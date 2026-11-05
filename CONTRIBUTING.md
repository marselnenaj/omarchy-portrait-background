# Contributing

Start with the tests in the README. Keep the runtime dependency-free and theme manifests data-only.
Change the canonical files under `plugin/` and the patch specification, then regenerate the review
snapshot with `python3 tools/prepare-marketplace.py` on an explicitly tested Omarchy host.
Run the actual Omarchy validator before releasing. Record the tested package version and source hash.

For a bug report, include your Omarchy version, plugin version and the output of
`./portrait-background status --live --json`. Review that output before posting: it includes local
paths and monitor names. Describe what each screen showed, its resolution, rotation and scale,
and whether the problem happened during a theme switch, video playback or a display change.

Keep plugin and data-contract identifiers stable. Bump the plugin version in the patch specification
and PortraitMapping.qml together. Runtime changes belong here first; downstream integrations can
vendor a pinned copy. See docs/compatibility.md.
