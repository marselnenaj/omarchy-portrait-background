# Changelog

## 1.0.3 — 2026-11-05

First public release. Versions through 1.0.2 were internal development builds.

- Theme-provided portrait and square wallpapers, matched to each monitor's logical shape.
- Retains Omarchy's background renderer, transitions, intros, video handling and background CLI.
- Python installer with plans by default, explicit apply, backups, rollback and safe removal.
- Restores the working plugin if publishing an update fails; rollback validates staged files too.
- Requires Omarchy's validator before publishing an installation and rederives outdated files before enabling.
- Includes both project and upstream license notices in generated installations.
- Gives runtime file-processing commands a ten-second deadline.
- Rejects truncated PNG headers and nonadvancing JPEG segments in the theme-author tool.
- Includes a root manifest and a reproducible source snapshot for manual-setup marketplace review.
- Adds an illustrated README, launch artwork, release notes and expanded regression coverage.

Live rotation changes, hotplug and rescaling remain unqualified. Lock-screen backgrounds are outside this plugin.
