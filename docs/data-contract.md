# The portrait runtime manifest, format 1

A theme opts in with `displays/portrait-runtime.json` in its own folder. Omarchy copies the theme to
`~/.local/state/omarchy/current/theme/` when it is applied, and the plugin reads it there at each background change.
The file is data only and treated as untrusted. `plugin/PortraitRuntime.js` is the reference implementation: what it
accepts is the contract.

## The file

| Field | Rule |
|---|---|
| `kind` | `"bogen-portrait-runtime"` |
| `format` | `1` |
| `theme` | optional, the theme's folder name, `[a-z0-9][a-z0-9._-]{0,63}`; shown in the status only |
| `appliesTo` | optional, `"theme-backgrounds"`: compositions replace the theme's own backgrounds only |
| `wallpapers` | at most 6 entries; more are ignored and reported |
| `incomplete` | optional, at most 6 `{ aspect, status, reason }`: shapes not designed yet, reported, never shown |

The whole file is at most 64 KB, a regular file, not a link.

## A wallpaper entry

| Field | Rule |
|---|---|
| `aspect` | `"9:16"`, `"10:16"`, `"1:1"`…: numbers up to three digits with up to three decimals |
| `width`, `height` | whole pixels, 320 to 16384, within 1.5 % of `aspect`, not landscape |
| `orientation` | optional; if given, it must be what the size says: `portrait` or `square` |
| `file` | `displays/<name>.png`, `.jpg`, `.jpeg` or `.webp`: lower case, directly in `displays/`, no `..` |
| `sha256` | 64 lower-case hex digits: the file's bytes |
| `bytes` | the file's size, 1 byte to 48 MB |
| `status` | `"artwork"` or `"composed"`. Any other status is listed as incomplete and never shown |

One entry per aspect: a second of the same aspect is ignored.

## What the plugin checks before showing a picture

1. The theme folder and the file are resolved without links: the file must be exactly `<theme>/<file>`.
2. It is a regular file of at most 48 MB.
3. It is copied into `~/.cache/bogen/portrait-background/<sha256>.<ext>` (a private folder, 0700), and the copy's
   sha256 must equal the manifest's; otherwise the copy is deleted.
4. The copy's byte count and its header (PNG IHDR, JPEG SOF, WebP VP8/VP8L/VP8X) must match `bytes`, `width`,
   `height` and the format its extension names.

The copy is what is drawn, so a file changed after the check is never shown. Copies no current or on-screen frame
uses are deleted after each check.

## Which screen shows what

A screen takes the entry whose width and height ratio is within 1.5 % of its own logical shape. Logical shape means
the mode, turned and mirrored as mounted, divided by the scale. Landscape screens never take one. With two entries of
the same shape, the larger wins. It is decoded at the screen's size, as Omarchy decodes its own backgrounds, so a
picture larger than the screen costs the screen's pixels, not its own.

A composition replaces only the theme's own stills: files directly in the current theme's `backgrounds/`. A video
background, a picture you picked from elsewhere, or a theme without the manifest keeps Omarchy's behaviour.

## Making one

`tools/make-runtime-manifest.py <theme-folder> displays/<picture> …` measures each picture from its header and writes
the manifest. It refuses landscape pictures, links, other formats, and two pictures of one shape. Then apply the
theme again, for example with `omarchy theme set <theme>`.
