# Compatibility and keeping one source

## Names kept from Bogen

The plugin was first written in [Bogen](https://github.com/marselnenaj/bogen), a design tool that exports Omarchy
themes. Several names keep that origin, so that themes Bogen exports, and Bogen's own `bogen omarchy portrait …`
installer, work with an install made here, and the other way round:

| Name | Where |
|---|---|
| `bogen.portrait-background` | the plugin id, its folder under `~/.config/omarchy/plugins/`, and its marker in `Background.qml` |
| `bogen.plugin: "portrait-background"` | the ownership mark in the installed `manifest.json`; with the id, it tells this plugin from any other folder |
| `~/.local/state/bogen/portrait-background/` | `install.json` and `backups/<UTC time>` |
| `~/.cache/bogen/portrait-background/` | the verified copies the plugin draws |
| `"kind": "bogen-portrait-runtime"` | the theme manifest |

Changing them would orphan existing installs and themes, so they stay. The product is this repository.
`manifest.json` records which installer wrote it (`bogen.installer`), and `status` shows it.

## Living beside Bogen's installer

Both installers:
- derive `Background.qml` with the same anchors (this repository's `patch/background-patch.json` was generated from
  Bogen's source, and the derived file is identical below its four header lines);
- record the same ownership mark, plugin version, patch number, stock sha256 and file hashes;
- use the same backup folder and names.

So `status` here reads a Bogen install as this plugin, outdated when its version, patch or stock sha256 differs. An
`install --apply` here replaces it after a backup, and the reverse is also true. A file edited by hand stops both
until `--force`.

## One source, versions in step

The canonical runtime is `plugin/PortraitMapping.qml`, `plugin/PortraitRuntime.js` and
`patch/background-patch.json`, at the plugin version in `background-patch.json` (`pluginVersion`, which
`PortraitMapping.qml` also reports at runtime). To keep one source:

1. Change the runtime here first, bump `pluginVersion` (and `patch` when an anchor changes), and keep the tests green.
2. Copy the two plugin files and the anchors into a dependent project as a pinned version, byte for byte. A test
   there should compare the derived `Background.qml` and the two files with this repository's at that version.
3. Neither side fetches the other at build or run time.

At the time of writing the files here are byte-identical to Bogen's integration, version 1.0.2, patch 1.
