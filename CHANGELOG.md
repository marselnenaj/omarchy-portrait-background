# Changelog

## Unreleased

Nothing is tagged or released yet. The plugin files report version 1.0.2, the same files as Bogen's integration at
the time of writing (see docs/compatibility.md).

- The standalone installer (`./portrait-background`): Python 3 standard library, plan by default, `--apply` to
  change anything; install, enable, disable, rollback, remove and status, with the same ownership marks, state folder
  and backups as Bogen's installer.
- The runtime, plugin 1.0.2: portrait screens take the composition when a theme is applied again on the same
  background; the status forgets the previous theme after a switch to one without a manifest; `status --live`
  says when the running shell still has an older copy.
- `tools/make-runtime-manifest.py` for theme authors, and a synthetic example.
