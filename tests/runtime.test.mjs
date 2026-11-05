// The plugin's own PortraitRuntime.js, loaded the way the shell loads it (minus the QML pragma line), with Node's
// built-in test runner: no dependencies, no graphical shell.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const names = ['KIND', 'FORMAT', 'decodeBase64', 'imageHeader', 'validateManifest', 'parseManifestText', 'parseKeyLines', 'verifyAsset', 'isThemeStill', 'entryFor', 'screenPath', 'pathsOf', 'mapsAfterResolve', 'displayedMapAtRevealEnd', 'displayedMapOnPathChange', 'orientationOf', 'outcome'];
const src = readFileSync(join(root, 'plugin', 'PortraitRuntime.js'), 'utf8').replace(/^\.pragma library\s*$/m, '');
const lib = new Function(`"use strict";\n${src}\nreturn { ${names.join(', ')} };`)();

const png = (w, h) => {
  const b = Buffer.alloc(64);
  Buffer.from('89504e470d0a1a0a0000000d49484452', 'hex').copy(b, 0);
  b.writeUInt32BE(w, 16);
  b.writeUInt32BE(h, 20);
  return b;
};
const entry = (over = {}) => ({ aspect: '9:16', orientation: 'portrait', width: 2160, height: 3840, file: 'displays/portrait-9x16.png', sha256: 'a'.repeat(64), bytes: 1000, status: 'artwork', ...over });
const manifest = (wallpapers, extra = {}) => ({ kind: 'bogen-portrait-runtime', format: 1, theme: 'example', appliesTo: 'theme-backgrounds', wallpapers, incomplete: [], ...extra });

test('the example manifest is what the plugin reads: one composition shown, the other listed as incomplete', () => {
  const check = lib.parseManifestText(readFileSync(join(root, 'examples', 'portrait-runtime.example.json'), 'utf8'));
  assert.equal(check.ok, true);
  assert.deepEqual(check.entries.map((e) => [e.aspect, e.file, e.format]), [['9:16', 'displays/portrait-9x16.png', 'png']]);
  assert.deepEqual(check.incomplete.map((i) => [i.aspect, i.status]), [['10:16', 'needs-design']]);
});

test('only designed compositions are shown; anything else is incomplete', () => {
  for (const status of ['needs-design', 'mismatch', 'unverified', 'missing', 'placeholder', '']) {
    assert.deepEqual(lib.validateManifest(manifest([entry({ status })])).entries, [], status);
  }
  assert.equal(lib.validateManifest(manifest([entry({ status: 'composed' })])).entries.length, 1);
});

test('refuses paths out of displays/, other formats, wrong shapes, landscape, oversize and malformed manifests', () => {
  for (const bad of [
    entry({ file: '../../.ssh/id.png' }), entry({ file: 'displays/../colors.png' }), entry({ file: '/etc/x.png' }), entry({ file: 'backgrounds/1.png' }),
    entry({ file: 'displays/x.svg' }), entry({ file: 'displays/x.gif' }), entry({ sha256: 'z'.repeat(64) }), entry({ bytes: 100 * 1024 * 1024 }),
    entry({ width: 3840, height: 2160 }), entry({ aspect: '16:9', width: 3840, height: 2160 }), entry({ orientation: 'landscape' }),
  ]) assert.deepEqual(lib.validateManifest(manifest([bad])).entries, [], JSON.stringify(bad));
  assert.equal(lib.validateManifest({ ...manifest([entry()]), format: 2 }).ok, false);
  assert.equal(lib.parseManifestText('x'.repeat(70000)).ok, false);
  assert.equal(lib.parseManifestText('{').ok, false);
});

test('a portrait screen of the shape gets the composition; landscape, other shapes, videos and failures keep the global background', () => {
  const map = { entries: [{ aspect: '9:16', width: 2160, height: 3840, path: '/c/a.png' }] };
  assert.equal(lib.screenPath('/t/backgrounds/1.png', map, 2160, 3840), '/c/a.png');
  assert.equal(lib.screenPath('/t/backgrounds/1.png', map, 1440, 2560), '/c/a.png');
  assert.equal(lib.screenPath('/t/backgrounds/1.png', map, 3840, 2160), '/t/backgrounds/1.png');
  assert.equal(lib.screenPath('/t/backgrounds/1.png', map, 1200, 1920), '/t/backgrounds/1.png');
  assert.equal(lib.screenPath('/t/backgrounds/loop.mp4', map, 2160, 3840), '/t/backgrounds/loop.mp4');
  assert.equal(lib.screenPath('/t/backgrounds/1.png', map, 2160, 3840, { '/c/a.png': true }), '/t/backgrounds/1.png');
  assert.equal(lib.isThemeStill('/h/.config/omarchy/backgrounds/x/mine.jpg', ['/h/.local/state/omarchy/current/theme']), false);
});

test('a theme applied again on the same still: the displayed frame takes the new map though its path never changed', () => {
  const theme = '/h/.local/state/omarchy/current/theme';
  const still = `${theme}/backgrounds/1.png`;
  const map = { themeDirs: [theme], entries: [{ aspect: '9:16', width: 2160, height: 3840, path: '/c/a.png' }] };
  const mapFor = (p) => (lib.isThemeStill(p, map.themeDirs) ? map : null);
  // Omarchy's reveal is running toward the same path when the map arrives, then ends without a path change.
  const frames = { incoming: '/snap/next.png', current: still, displayed: still, revealProgress: 0, incomingMap: null, displayedMap: null };
  const during = lib.mapsAfterResolve(frames, mapFor);
  assert.equal(during.incomingMap, map);
  assert.equal(during.displayedMap, null);
  const end = lib.displayedMapAtRevealEnd({ ...frames, ...during, revealProgress: 1 });
  assert.equal(end, map);
  // Checked again with the reveal over and the incoming frame left set, as Omarchy leaves it.
  const refreshed = lib.mapsAfterResolve({ ...frames, revealProgress: 1, incomingMap: map, displayedMap: null }, mapFor);
  assert.equal(refreshed.displayedMap, map);
});

test('the author tool writes a manifest the plugin accepts, measured from the picture itself', () => {
  const dir = mkdtempSync(join(tmpdir(), 'portrait-example-'));
  try {
    execFileSync('python3', ['-I', join(root, 'examples', 'make-example-theme.py'), join(dir, 'theme')]);
    const text = readFileSync(join(dir, 'theme', 'displays', 'portrait-runtime.json'), 'utf8');
    const check = lib.parseManifestText(text);
    assert.equal(check.ok, true, JSON.stringify(check.problems));
    const [e] = check.entries;
    assert.deepEqual([e.aspect, e.width, e.height, e.format], ['9:16', 1080, 1920, 'png']);
    const bytes = readFileSync(join(dir, 'theme', e.file));
    const report = { path: '/cache/x.png', bytes: String(bytes.length), header: bytes.subarray(0, 262144).toString('base64') };
    assert.equal(lib.verifyAsset(e, report).ok, true);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('measures headers and refuses what it cannot measure', () => {
  assert.deepEqual(lib.imageHeader(png(2160, 3840)), { format: 'png', width: 2160, height: 3840 });
  assert.equal(lib.imageHeader(Buffer.from('GIF89a' + '\0'.repeat(30), 'latin1')), null);
  assert.equal(lib.imageHeader(png(0, 10)), null);
  const e = lib.validateManifest(manifest([entry()])).entries[0];
  assert.equal(lib.verifyAsset(e, { status: 'sha' }).ok, false);
  assert.equal(lib.verifyAsset(e, { path: '/c/a.png', bytes: '1000', header: png(3840, 2160).toString('base64') }).ok, false);
});

test('after switching to a theme without a manifest, the status names no theme or revision', () => {
  const map = { entries: [{ aspect: '9:16', width: 2160, height: 3840, path: '/c/a.png' }] };
  assert.equal(lib.outcome(map, 'active', { theme: 'example', revision: 'abcdef012345' }).theme, 'example');
  for (const state of ['no-manifest', 'no-theme', 'error']) {
    assert.deepEqual(lib.outcome(null, state, { theme: 'example', revision: 'abcdef012345' }), { map: null, state, theme: '', revision: '', problems: [], incomplete: [], rejected: [] });
  }
});
