# omarchy-portrait-background

A portrait monitor on [Omarchy](https://omarchy.org) shows the middle of the landscape background, cropped. This
plugin lets a theme ship its own portrait picture, and draws it on every monitor of that shape. Landscape monitors keep
the theme background as before.

It is a user clone of Omarchy's own background plugin, so theme switches, background cycling, intros, video
backgrounds, double-click actions and `omarchy-shell background …` keep working. Its `Background.qml` is derived
from the one your Omarchy ships, at install time. Nothing in `/usr/share/omarchy` is changed.

Status: not released or tagged yet. The installer and runtime are tested offline (see [Tests](#tests)). The runtime
has run in a real Omarchy shell on a 4K monitor turned 270° beside a 4K landscape one. Rotation changes, hotplug and
rescaling in a live session have not been checked yet.

## Requirements

- Omarchy with the shell background plugin (`$OMARCHY_PATH/shell/plugins/background/Background.qml`, by default
  under `/usr/share/omarchy`). The installer checks that file before writing anything.
- `python3` (ships with Omarchy) and `git`. No Node, npm or Bogen.
- Linux desktop only: a Mac or a phone cannot run an Omarchy shell plugin.

## Install

```bash
git clone https://github.com/marselnenaj/omarchy-portrait-background ~/.local/share/omarchy-portrait-background
cd ~/.local/share/omarchy-portrait-background

./portrait-background status            # what is there now; changes nothing
./portrait-background install           # plan only
./portrait-background install --apply   # writes ~/.config/omarchy/plugins/bogen.portrait-background
./portrait-background enable --apply    # omarchy plugin enable bogen.portrait-background
```

Every action only plans and prints until you add `--apply`. Installing does not enable anything, and enabling is a
separate step. Run it as yourself, never with sudo: it writes only to your own config and state folders.

`omarchy plugin add <url>` does **not** work for this repository, by design: that command clones a repository as the
plugin itself, and this plugin's `Background.qml` must be derived from your machine's Omarchy first. Likewise
`omarchy plugin update` only fast-forwards plugins that are git checkouts, which the installed plugin is not.

## Update

```bash
cd ~/.local/share/omarchy-portrait-background
git pull --ff-only
./portrait-background install           # plan
./portrait-background install --apply   # replaces the plugin's files; the old ones are backed up
./portrait-background status --live
```

After an `omarchy update`, `status` reports the plugin as outdated when the stock `Background.qml` changed. If the
new stock file still has every line the patch anchors on, `install --apply` derives the plugin again. If it does not,
the installer refuses and writes nothing. Then run `disable --apply` to go back to Omarchy's own background until a
version of this repository knows the new file.

Omarchy reloads a plugin when its files change, but can keep QML it has already loaded. `status --live` asks the
running shell for the version it runs. If that differs from the installed version, it says so, and
`omarchy restart shell` loads the new one. A restart is needed only then.

## Disable, roll back, remove

```bash
./portrait-background disable --apply    # omarchy plugin disable: Omarchy re-enables omarchy.background
./portrait-background rollback --apply   # put back the previous version of the plugin's files
./portrait-background remove --apply     # move the files to a backup; refused while enabled
```

`omarchy plugin remove bogen.portrait-background` also works. It disables the plugin, which restores Omarchy's
background, and moves the folder to a backup under `~/.config/omarchy/plugins/`.

## Safeguards

- **Fails closed.** The patch is a list of exact line replacements (`patch/background-patch.json`). Each must match
  the stock file exactly once, or nothing is derived and nothing is written. A file that is already patched is
  refused as a source.
- **Never takes over what is not its own.** A folder `bogen.portrait-background` that this plugin did not make is
  never written over. Enabling is refused when another clone of `omarchy.background` is installed, or when you
  disabled `omarchy.background` yourself (something else may draw your wallpaper).
- **Keeps your edits.** Files you changed by hand are not replaced without `--force`. Every replaced version is
  backed up to `~/.local/state/bogen/portrait-background/backups/`.
- **No links followed when writing.** New files are created with `O_EXCL | O_NOFOLLOW` in a fresh staging folder,
  then swapped in. The staged folder passes `omarchy plugin validate` first.
- **The desktop always has a background.** `remove` is refused while the plugin is enabled. Disabling always
  brings back `omarchy.background`.
- **Bounded commands.** It runs only `omarchy plugin validate|enable|disable`, `omarchy-shell shell rescanPlugins`
  and, with `--live`, `omarchy-shell background portraitStatus`, as argument lists with timeouts. Nothing runs as
  root.

## What a theme ships

A theme opts in with one data file, `displays/portrait-runtime.json`, next to its pictures in `displays/`. Nothing
in it is run.

```json
{
  "kind": "bogen-portrait-runtime",
  "format": 1,
  "theme": "example",
  "appliesTo": "theme-backgrounds",
  "wallpapers": [
    {
      "aspect": "9:16", "orientation": "portrait", "width": 2160, "height": 3840,
      "file": "displays/portrait-9x16.png",
      "sha256": "<sha256 of the file>", "bytes": 1234567, "status": "artwork"
    }
  ],
  "incomplete": []
}
```

You don't need Bogen or any agent to make one. Put your own portrait PNG, JPEG or WebP in the theme's `displays/`
folder and run:

```bash
python3 tools/make-runtime-manifest.py ~/.config/omarchy/themes/<theme> displays/portrait-9x16.png
omarchy theme set <theme>
```

`python3 examples/make-example-theme.py /tmp/example-theme` makes a small synthetic theme folder that shows the
files. Its picture is drawn in code. [docs/data-contract.md](docs/data-contract.md) has every rule.

## What each screen shows

| Screen | Shows |
|---|---|
| Landscape | the theme background, as stock Omarchy draws it |
| Portrait or square, a listed composition of its shape (within 1.5 %) | that composition, decoded at the screen's size |
| Portrait without a composition of its shape | the theme background, cropped, as stock |
| Any screen while a video background plays | the video: OWE owns video backgrounds |
| A picture you chose from outside the theme's `backgrounds/` | that picture, as stock |
| A composition that is missing, changed, oversized, a link, or fails to load | the theme background |

The shape is the monitor's logical size: its mode, turned and mirrored as mounted, divided by its scale.

## Limits

- The lock screen is a separate Omarchy plugin and still shows the theme background on every screen.
- A theme's intro video plays as Omarchy plays it. The portrait composition appears with the still that follows.
- During a theme switch the reveal waits at most 1.5 s for the new theme's pictures to be checked. If the check
  takes longer, a portrait screen first shows the theme background, then switches without an animation.
- Compositions are taken only as `artwork` or `composed`. A placeholder or anything marked incomplete is never shown.

## Compatibility with Bogen

The plugin id is `bogen.portrait-background`, and its state lives under `~/.local/state/bogen/portrait-background`.
These names come from [Bogen](https://github.com/marselnenaj/bogen), where the plugin was first written, and are
kept so that Bogen's exported themes and Bogen's own installer (`bogen omarchy portrait …`) work with the same
install. Either installer recognises and can update or roll back the other's. This repository does not need Bogen
and does not talk to it. See [docs/compatibility.md](docs/compatibility.md).

## Tests

```bash
python3 -m unittest discover -s tests -v   # patch anchors and refusals, installer safety in a made-up home
node --test tests/                         # the shipped PortraitRuntime.js: manifest checks, screen choice, frame maps
```

Neither needs a graphical shell or touches your home. The installer tests use stand-ins for `omarchy` and
`omarchy-shell`. CI runs both on every push.

## License

MIT, see [LICENSE](LICENSE) and [NOTICE](NOTICE).
