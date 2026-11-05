# Portrait Background 1.0.3

Give your Omarchy theme a portrait mode. This first standalone release lets themes ship separate
portrait or square artwork and selects the matching composition for each monitor. Landscape
monitors keep the normal wallpaper. Themes without matching artwork keep Omarchy's usual fallback.

The plugin derives its renderer from your installed Omarchy, preserving the background service's
transitions, cycling, intro/video handling and CLI. Python 3 and the normal Omarchy tools are enough;
Bogen is not required. The repository includes a theme-author tool and a synthetic example.

## Install

Use the versioned installer instructions in the [README](https://github.com/marselnenaj/omarchy-portrait-background/tree/v1.0.3#quick-start).
Do not use `omarchy plugin add` for this release: the generated review snapshot targets the tested
Omarchy package, while the installer derives from your own installed renderer.

Every modifying action requires `--apply`. Updates keep backups; disable restores the built-in
background; rollback and removal are available. The installer preserves hand edits unless forced
and restores the previous folder if publishing an update fails.

## Validation and limits

34 automated tests passed, together with the real Omarchy manifest validator, Qt 6 parsing,
snapshot regeneration, the marketplace preview optimizer and a separate Quickshell integration
check. The tested host runs Omarchy 4.5.0-3 with a 4K landscape and a rotated 4K portrait monitor.
See [release validation](https://github.com/marselnenaj/omarchy-portrait-background/blob/v1.0.3/docs/release-validation.md) for what each check establishes.

Themes must provide the portrait image; the plugin does not generate artwork. Live display
hotplug, rotation changes and rescaling remain unqualified. The lock screen is separate.

MIT licensed. Source archive and SHA256SUMS accompany this release. Marketplace listing is a
separate maintainer-reviewed process; submitting the plugin does not mean it is already listed.
