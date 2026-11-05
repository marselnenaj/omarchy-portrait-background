#!/usr/bin/env python3
"""Install, update, enable, disable, roll back and remove the Omarchy portrait background plugin.

Python 3 standard library only. Every action plans and prints by default; only --apply changes anything.

The plugin is a user clone of Omarchy's own background plugin (omarchy.clonedFrom = omarchy.background). Its
Background.qml is derived at install time from the Background.qml this machine's Omarchy ships, by the exact
replacements in patch/background-patch.json; a stock file that does not match them is refused and nothing is
written. The plugin's other files are copied from plugin/ as they are.

Writes go only to ~/.config/omarchy/plugins/bogen.portrait-background and
~/.local/state/bogen/portrait-background (the same places, ownership marks and backup layout as Bogen's own
installer, so either can manage an install the other made). Nothing runs as root. $OMARCHY_PATH is only read.
Commands run as argument lists with timeouts, never through a shell: omarchy-shell shell rescanPlugins,
omarchy plugin validate|enable|disable, and, when asked, omarchy-shell background portraitStatus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATCH_FILE = ROOT / "patch" / "background-patch.json"
PLUGIN_SOURCE = ROOT / "plugin"
OWN_FILES = ("PortraitMapping.qml", "PortraitRuntime.js")

# The id stays bogen.portrait-background: it is what Bogen's exports and its own installer know, and what the
# running shell routes the background to. The product is this repository.
PLUGIN_ID = "bogen.portrait-background"
PLUGIN_NAME = "Portrait Background"
STOCK_ID = "omarchy.background"
OWNER_MARK = "portrait-background"
INSTALLER = "omarchy-portrait-background"

MAX_QML = 512 * 1024
MAX_MANIFEST = 64 * 1024
MAX_SHELL_JSON = 4 * 1024 * 1024
MAX_PLUGIN_DIRS = 256
COMMAND_TIMEOUT = 10
BACKUP_NAME = re.compile(r"^\d{8}T\d{6}Z(-\d+)?$")


class Refused(Exception):
    """An action that cannot be done safely. Nothing was written."""


# ---------------------------------------------------------------- the patch


def load_spec(path: Path = PATCH_FILE) -> dict:
    spec = json.loads(path.read_text(encoding="utf-8"))
    if spec.get("format") != 1 or spec.get("plugin") != OWNER_MARK:
        raise Refused(f"{path} is not a format 1 patch specification for this plugin.")
    if not isinstance(spec.get("anchors"), list) or not spec["anchors"]:
        raise Refused(f"{path} has no anchors.")
    return spec


SPEC = load_spec()
PLUGIN_VERSION: str = SPEC["pluginVersion"]
PATCH_VERSION: int = SPEC["patch"]
MARK: str = SPEC["marker"]


@dataclass
class PatchResult:
    ok: bool
    source: str = ""
    missing: list[str] = field(default_factory=list)
    reason: str = ""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def patch_background(stock: str, spec: dict = SPEC, stock_sha: str | None = None) -> PatchResult:
    """Omarchy's Background.qml with the portrait patch, or why it cannot be patched. Pure."""
    stock_sha = stock_sha or sha256_text(stock)
    if spec["marker"] in stock:
        return PatchResult(False, reason="The file is already patched; derive from the stock file only.")
    for req in spec.get("requires", []):
        if not re.search(req["pattern"], stock):
            return PatchResult(False, missing=[req["name"]], reason="The file has no \"background\" IPC target, so it is not Omarchy's background plugin.")
    missing = [a["name"] for a in spec["anchors"] if stock.count(a["find"]) != 1]
    if missing:
        return PatchResult(False, missing=missing, reason=(
            f"Omarchy's Background.qml changed where the patch goes ({', '.join(missing)}). This version does not know the new "
            "file, so it derives nothing; the stock background stays in use."))
    out = stock
    for a in spec["anchors"]:
        out = out.replace(a["find"], a["replace"], 1)
    header = "\n".join([
        f"{spec['marker']} {spec['pluginVersion']} (patch {spec['patch']})",
        f"// Derived by omarchy-portrait-background from Omarchy's own shell/plugins/background/Background.qml (sha256 {stock_sha}),",
        "// MIT License, https://github.com/basecamp/omarchy. Every changed line is marked; PortraitMapping.qml holds the rest.",
        "// Editing this file by hand is fine: the installer then refuses to replace it without --force, and keeps a backup.",
        "",
    ])
    return PatchResult(True, source=header + out)


# ---------------------------------------------------------------- where things are


@dataclass
class Env:
    home: Path
    omarchy_path: Path
    omarchy_bin: str
    shell_bin: str

    @property
    def plugins_dir(self) -> Path:
        return self.home / ".config" / "omarchy" / "plugins"

    @property
    def target(self) -> Path:
        return self.plugins_dir / PLUGIN_ID

    @property
    def state_dir(self) -> Path:
        return self.home / ".local" / "state" / "bogen" / "portrait-background"

    @property
    def state_base(self) -> Path:
        """~/.local/state: the person's, links and all. Everything this installer makes below it is checked."""
        return self.home / ".local" / "state"

    @property
    def backups_dir(self) -> Path:
        return self.state_dir / "backups"

    @property
    def shell_json(self) -> Path:
        return self.home / ".config" / "omarchy" / "shell.json"

    @property
    def stock_dir(self) -> Path:
        return self.omarchy_path / "shell" / "plugins" / "background"


def find_bin(name: str, omarchy_path: Path) -> str:
    found = shutil.which(name)
    if found:
        return found
    own = omarchy_path / "bin" / name
    return str(own) if own.is_file() else name


def env_from(environ: dict[str, str] = os.environ) -> Env:  # type: ignore[assignment]
    home = Path(environ.get("HOME") or Path.home())
    omarchy_path = Path(environ.get("OMARCHY_PATH") or "/usr/share/omarchy")
    return Env(home, omarchy_path, find_bin("omarchy", omarchy_path), find_bin("omarchy-shell", omarchy_path))


# ---------------------------------------------------------------- reading, without following links


def exists(path: Path) -> bool:
    try:
        os.lstat(path)
        return True
    except OSError:
        return False


def is_link(path: Path) -> bool:
    try:
        return stat.S_ISLNK(os.lstat(path).st_mode)
    except OSError:
        return False


def read_small(path: Path, limit: int) -> str | None:
    """A regular file (not a link) of at most `limit` bytes, as text."""
    try:
        st = os.lstat(path)
        if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
            return None
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as f:
            if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
                return None
            data = f.read(limit + 1)
            return data.decode("utf-8") if len(data) <= limit else None
    except (OSError, UnicodeDecodeError):
        return None


def read_json(path: Path, limit: int = MAX_MANIFEST):
    text = read_small(path, limit)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


# ---------------------------------------------------------------- status


def shell_config(env: Env) -> tuple[list[str], list[str]]:
    raw = read_json(env.shell_json, MAX_SHELL_JSON)
    if not isinstance(raw, dict):
        return [], []

    def ids(v) -> list[str]:
        if not isinstance(v, list):
            return []
        out = []
        for p in v[:1024]:
            s = str(p.get("id", "")) if isinstance(p, dict) else str(p or "")
            if s:
                out.append(s)
        return out

    return ids(raw.get("plugins")), ids(raw.get("disabledPlugins"))


def list_backups(env: Env) -> list[str]:
    try:
        names = [n for n in os.listdir(env.backups_dir) if BACKUP_NAME.match(n)]
    except OSError:
        return []
    return sorted(names, reverse=True)


def status(env: Env) -> dict:
    stock_path = env.stock_dir / "Background.qml"
    stock_text = read_small(stock_path, MAX_QML)
    stock_manifest = read_json(env.stock_dir / "manifest.json")
    stock_sha = sha256_text(stock_text) if stock_text is not None else None
    patched = patch_background(stock_text, SPEC, stock_sha) if stock_text is not None else None
    stock: dict = {"path": str(stock_path), "present": stock_text is not None, "compatible": bool(patched and patched.ok)}
    if stock_sha:
        stock["sha256"] = stock_sha
    if isinstance(stock_manifest, dict) and isinstance(stock_manifest.get("version"), str):
        stock["version"] = stock_manifest["version"][:32]
    if patched and not patched.ok:
        stock["reason"] = patched.reason
        stock["missing"] = patched.missing
    elif stock_text is None:
        stock["reason"] = f"There is no {stock_path}: this is not an Omarchy desktop with the shell background plugin."

    installed = None
    if exists(env.target):
        manifest = read_json(env.target / "manifest.json")
        meta = manifest.get("bogen") if isinstance(manifest, dict) and isinstance(manifest.get("bogen"), dict) else None
        ours = not is_link(env.target) and isinstance(manifest, dict) and manifest.get("id") == PLUGIN_ID and bool(meta) and meta.get("plugin") == OWNER_MARK
        modified: list[str] = []
        files = meta.get("files") if meta and isinstance(meta.get("files"), dict) else {}
        if ours:
            for name, digest in list(files.items())[:16]:
                if not re.fullmatch(r"[\w.-]+", name):
                    continue
                text = read_small(env.target / name, MAX_QML)
                if text is None or sha256_text(text) != digest:
                    modified.append(name)
        version = manifest.get("version")[:32] if isinstance(manifest, dict) and isinstance(manifest.get("version"), str) else None
        derived = meta.get("stockSha256") if meta and isinstance(meta.get("stockSha256"), str) else None
        installed = {
            "dir": str(env.target), "ours": ours, "modified": modified, "version": version, "stockSha256": derived,
            "installer": meta.get("installer", "bogen") if meta else None,
            "outdated": ours and (version != PLUGIN_VERSION or meta.get("patch") != PATCH_VERSION or (bool(stock_sha) and derived != stock_sha)),
        }

    plugins, disabled = shell_config(env)
    conflicts = []
    try:
        dirs = sorted(n for n in os.listdir(env.plugins_dir) if not n.startswith("."))[:MAX_PLUGIN_DIRS]
    except OSError:
        dirs = []
    for name in dirs:
        m = read_json(env.plugins_dir / name / "manifest.json")
        if not isinstance(m, dict) or not isinstance(m.get("omarchy"), dict) or m["omarchy"].get("clonedFrom") != STOCK_ID:
            continue
        cid = str(m.get("id", name))
        if cid == PLUGIN_ID:
            continue
        conflicts.append({"id": cid, "dir": str(env.plugins_dir / name), "enabled": cid in plugins and cid not in disabled})

    enabled = bool(installed and installed["ours"]) and PLUGIN_ID in plugins and PLUGIN_ID not in disabled
    stock_disabled = STOCK_ID in disabled
    state = "foreign" if installed and not installed["ours"] else "enabled" if enabled else "installed" if installed else "not-installed"
    nxt: list[str] = []
    entry = "./portrait-background"
    if not stock["present"]:
        summary = "Omarchy's background plugin is not on this machine, so the portrait background cannot be installed here (a Mac or a phone cannot run a desktop shell plugin)."
    elif state == "foreign":
        summary = f"{env.target} exists and is not this plugin; it is never written over."
    elif conflicts:
        summary = f"Another clone of the background plugin is installed ({', '.join(c['id'] for c in conflicts)}). This plugin is not enabled beside it; merge the portrait patch into yours, or remove yours first."
    elif not stock["compatible"] and state == "not-installed":
        summary = stock.get("reason", "The stock background plugin cannot be patched.")
    elif state == "enabled":
        if installed["outdated"]:
            summary = "The portrait background is in use, derived from an older stock file or plugin version."
            nxt.append(f"{entry} install --apply   # derive again from the current stock file; a backup is kept" if stock["compatible"]
                       else f"{entry} disable --apply   # the new stock file cannot be patched; go back to the stock background")
        else:
            summary = "The portrait background is in use: portrait screens show the current theme's verified composition, the others the theme background."
    elif state == "installed":
        summary = "The portrait background plugin is installed but not enabled: every screen shows Omarchy's own background."
        if installed["outdated"] and stock["compatible"]:
            nxt.append(f"{entry} install --apply")
        nxt.append(f"{entry} enable --apply")
    else:
        summary = "The portrait background plugin is not installed: Omarchy shows one background on every screen, cropped to fill it."
        nxt += [f"{entry} install          # plan only", f"{entry} install --apply", f"{entry} enable --apply"]
    if stock_disabled and state != "enabled":
        nxt.insert(0, f"# omarchy.background is disabled in shell.json: something else may draw your wallpaper. This plugin is not enabled over that; re-enable it with: omarchy plugin enable {STOCK_ID}")
    return {
        "id": PLUGIN_ID, "version": PLUGIN_VERSION, "patch": PATCH_VERSION, "stock": stock, "installed": installed, "enabled": enabled,
        "stockDisabled": stock_disabled, "conflicts": conflicts, "state": state, "summary": summary, "next": nxt, "backups": list_backups(env),
    }


# ---------------------------------------------------------------- commands


def run(argv: list[str], timeout: int = COMMAND_TIMEOUT) -> str:
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as e:
        raise Refused(f"{argv[0]} is not installed.") from e
    except subprocess.TimeoutExpired as e:
        raise Refused(f"{' '.join(argv)} took longer than {timeout} s.") from e
    if done.returncode != 0:
        last = (done.stderr or done.stdout or "").strip().splitlines()[-1:] or [f"exit {done.returncode}"]
        raise Refused(f"{' '.join(argv)} failed: {last[0]}")
    return done.stdout.strip()


def live_status(env: Env) -> dict:
    try:
        text = run([env.shell_bin, "background", "portraitStatus"], timeout=3)
    except Refused as e:
        return {"liveError": str(e)}
    if len(text) > 256 * 1024:
        return {"liveError": "The plugin's report is too long."}
    try:
        return {"live": json.loads(text)}
    except ValueError:
        return {"liveError": f"The running background did not answer portraitStatus ({text[:120] or 'no output'}): this plugin is not the one drawing the background."}


def stale_runtime(installed_version: str | None, live) -> str | None:
    """When the running shell reports another plugin version than the installed one: Omarchy's hot reload can keep
    QML it already imported. Only when both are known and differ; then `omarchy restart shell` loads the new one."""
    running = live.get("version") if isinstance(live, dict) and isinstance(live.get("version"), str) else None
    if not installed_version or not running or running == installed_version:
        return None
    return f"The running shell still has plugin {running[:16]}, and {installed_version} is installed: its hot reload kept the code it had loaded. Run: omarchy restart shell"


# ---------------------------------------------------------------- building and writing


def build(env: Env) -> tuple[dict[str, str], str]:
    stock_path = env.stock_dir / "Background.qml"
    stock = read_small(stock_path, MAX_QML)
    if stock is None:
        raise Refused(f"There is no {stock_path}: this is not an Omarchy desktop with the shell background plugin. Nothing was written.")
    stock_sha = sha256_text(stock)
    patched = patch_background(stock, SPEC, stock_sha)
    if not patched.ok:
        raise Refused(f"{patched.reason} Nothing was written.")
    files = {"Background.qml": patched.source}
    for name in OWN_FILES:
        text = read_small(PLUGIN_SOURCE / name, MAX_QML)
        if text is None:
            raise Refused(f"This copy has no {PLUGIN_SOURCE / name}. Nothing was written.")
        files[name] = text
    stock_manifest = read_json(env.stock_dir / "manifest.json")
    meta = {"plugin": OWNER_MARK, "patch": PATCH_VERSION, "stockSha256": stock_sha}
    if isinstance(stock_manifest, dict) and isinstance(stock_manifest.get("version"), str):
        meta["stockVersion"] = stock_manifest["version"][:32]
    meta["files"] = {name: sha256_text(text) for name, text in files.items()}
    meta["installer"] = INSTALLER
    manifest = {
        "schemaVersion": 1, "id": PLUGIN_ID, "name": PLUGIN_NAME, "version": PLUGIN_VERSION, "author": "Marsel Nenaj", "license": "MIT",
        "description": "Omarchy's background, with the current theme's own verified composition on each portrait screen",
        "kinds": ["service"], "entryPoints": {"service": "Background.qml"}, "omarchy": {"clonedFrom": STOCK_ID}, "bogen": meta,
    }
    files["manifest.json"] = json.dumps(manifest, indent=2) + "\n"
    files["NOTICE"] = "\n".join([
        "Background.qml is derived at install time from the Omarchy background plugin installed on this machine",
        f"(shell/plugins/background/Background.qml, sha256 {stock_sha}), which is MIT licensed:",
        "https://github.com/basecamp/omarchy. The changes, PortraitMapping.qml and PortraitRuntime.js are MIT licensed",
        "as part of omarchy-portrait-background.",
        "",
    ])
    files["LICENSE"] = (ROOT / "LICENSE").read_text(encoding="utf-8")
    files["OMARCHY-LICENSE"] = (ROOT / "licenses" / "OMARCHY-MIT.txt").read_text(encoding="utf-8")
    return files, stock_sha


def write_new(path: Path, text: str, mode: int = 0o644) -> None:
    """A new file, never through a link and never over an existing one."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())


def remove_path(path: Path) -> None:
    """Removes a file, link or folder at `path` without following a link."""
    if not exists(path):
        return
    if is_link(path) or not stat.S_ISDIR(os.lstat(path).st_mode):
        os.unlink(path)
    else:
        shutil.rmtree(path)


def plain_dirs(path: Path, base: Path, mode: int = 0o755) -> None:
    """Makes `path` below `base` one folder at a time, refusing a link or a file at any level before creating anything."""
    rel = path.relative_to(base)
    here = base
    for part in rel.parts:
        here = here / part
        if is_link(here):
            raise Refused(f"{here} is a link. Nothing is written through it.")
        if exists(here):
            if not stat.S_ISDIR(os.lstat(here).st_mode):
                raise Refused(f"{here} is not a folder.")
            continue
        os.mkdir(here, mode)


def stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def backup(env: Env, source: Path) -> Path:
    env.state_base.mkdir(parents=True, exist_ok=True)
    plain_dirs(env.backups_dir, env.state_base, 0o700)
    os.chmod(env.state_dir, 0o700)
    dest = env.backups_dir / stamp()
    n = 2
    while exists(dest):
        dest = env.backups_dir / f"{stamp()}-{n}"
        n += 1
    shutil.copytree(source, dest, symlinks=True)
    return dest


def record_state(env: Env, patch: dict) -> None:
    env.state_base.mkdir(parents=True, exist_ok=True)
    plain_dirs(env.state_dir, env.state_base, 0o700)
    path = env.state_dir / "install.json"
    prev = read_json(path, MAX_MANIFEST)
    data = {**(prev if isinstance(prev, dict) else {}), **patch}
    tmp = env.state_dir / f".install.json.{os.getpid()}.tmp"
    remove_path(tmp)
    write_new(tmp, json.dumps(data, indent=2) + "\n", 0o600)
    os.replace(tmp, path)


def prepared_target(env: Env) -> Path:
    # ~/.config/omarchy/plugins may itself be a link the person made (dotfiles); Omarchy follows it, so does this.
    # Nothing below it is followed.
    env.plugins_dir.mkdir(parents=True, exist_ok=True)
    real = Path(os.path.realpath(env.plugins_dir))
    target = real / PLUGIN_ID
    if is_link(target):
        raise Refused(f"{target} is a link. Nothing is written through it.")
    return target


def contains_link(path: Path) -> bool:
    for root, dirs, files in os.walk(path, followlinks=False):
        for n in dirs + files:
            if is_link(Path(root) / n):
                return True
    return False


def publish_staging(staging: Path, target: Path) -> None:
    """Restore the previous working directory if publishing a staged update fails."""
    old = target.parent / f".{PLUGIN_ID}.bogen-old"
    had_target = exists(target)
    if exists(old):
        raise Refused(f"{old} is left from an interrupted update. Recover it before trying again.")
    if had_target:
        os.rename(target, old)
    try:
        os.rename(staging, target)
    except BaseException:
        if had_target:
            os.rename(old, target)
        raise
    if had_target:
        remove_path(old)


# ---------------------------------------------------------------- actions


@dataclass
class Plan:
    title: str
    possible: bool = True
    applied: bool = False
    blockers: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    commands: list[list[str]] = field(default_factory=list)
    backup: str | None = None
    notes: list[str] = field(default_factory=list)
    status: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def install(env: Env, apply: bool = False, force: bool = False) -> Plan:
    st = status(env)
    plan = Plan("Install", status=st)
    built = None
    try:
        built = build(env)
    except Refused as e:
        plan.blockers.append(str(e))
    if st["state"] == "foreign":
        plan.blockers.append(f"{env.target} exists and is not this plugin. It is never written over.")
    inst = st["installed"]
    if inst and inst["ours"] and inst["modified"] and not force:
        plan.blockers.append(f"You edited {', '.join(inst['modified'])} in {env.target}. Replacing them needs --force; a backup is kept.")
    up_to_date = bool(built and inst and inst["ours"] and not inst["outdated"] and not inst["modified"])
    if not plan.blockers:
        if up_to_date:
            plan.steps.append("Nothing to do: the installed plugin is this version, derived from the current stock file.")
        else:
            if inst and inst["ours"]:
                plan.steps.append(f"Back up {env.target} to {env.backups_dir}/<time>")
            plan.steps.append(f"Write {', '.join(built[0])} to {env.target}, Background.qml derived from {env.stock_dir / 'Background.qml'} (sha256 {built[1][:12]}…); the stock file is only read")
            plan.steps.append("The shell reloads the plugin on its own when its files change." if st["enabled"]
                              else "Nothing is enabled: every screen keeps Omarchy's background until `enable --apply`.")
    plan.possible = not plan.blockers
    if not apply or plan.blockers or up_to_date:
        return plan

    files, stock_sha = built
    # Check the state destination before replacing the working plugin.
    env.state_base.mkdir(parents=True, exist_ok=True)
    plain_dirs(env.state_dir, env.state_base, 0o700)
    target = prepared_target(env)
    staging = target.parent / f".{PLUGIN_ID}.bogen-new"
    remove_path(staging)
    os.mkdir(staging, 0o755)
    try:
        for name, text in files.items():
            write_new(staging / name, text)
        run([env.omarchy_bin, "plugin", "validate", str(staging)])
        if exists(target):
            plan.backup = str(backup(env, target))
        publish_staging(staging, target)
    except BaseException:
        remove_path(staging)
        raise
    record_state(env, {"installedAt": int(time.time() * 1000), "version": PLUGIN_VERSION, "stockSha256": stock_sha, "installer": INSTALLER, **({"backup": plan.backup} if plan.backup else {})})
    plan.applied = True
    plan.status = status(env)
    return plan


def enable(env: Env, apply: bool = False) -> Plan:
    st = status(env)
    plan = Plan("Enable", status=st)
    inst = st["installed"]
    if not inst or not inst["ours"]:
        plan.blockers.append("The plugin is not installed: run `install --apply` first.")
    elif "manifest.json" in inst["modified"]:
        plan.blockers.append("Its manifest.json was edited by hand; a plugin that cannot be vouched for is not enabled.")
    if st["conflicts"]:
        plan.blockers.append(f"Another clone of the background plugin is installed ({', '.join(c['id'] for c in st['conflicts'])}). Two clones fight over the background; this one is not enabled beside it.")
    if st["stockDisabled"] and not st["enabled"]:
        plan.blockers.append("omarchy.background is disabled in shell.json, so something else may draw the wallpaper. This plugin does not take over from it.")
    if inst and inst["ours"] and inst["outdated"] and not st["enabled"]:
        plan.blockers.append("The installed plugin is outdated. Run `install --apply` before enabling it on this Omarchy version.")
    commands = [[env.shell_bin, "shell", "rescanPlugins"], [env.omarchy_bin, "plugin", "enable", PLUGIN_ID]]
    if st["enabled"]:
        plan.steps.append("Nothing to do: it is enabled.")
    else:
        plan.steps += ["Rescan plugins so the shell knows the folder", f"Enable {PLUGIN_ID}: Omarchy disables omarchy.background and brings it back when this plugin is disabled"]
        plan.commands = commands
    plan.possible = not plan.blockers
    if not apply or plan.blockers or st["enabled"]:
        return plan
    for argv in commands:
        run(argv)
    record_state(env, {"enabledAt": int(time.time() * 1000)})
    plan.applied = True
    plan.status = status(env)
    return plan


def disable(env: Env, apply: bool = False) -> Plan:
    st = status(env)
    plan = Plan("Disable", status=st)
    if st["enabled"]:
        plan.steps.append(f"Disable {PLUGIN_ID}: Omarchy enables omarchy.background again")
        plan.commands = [[env.omarchy_bin, "plugin", "disable", PLUGIN_ID]]
    else:
        plan.steps.append("Nothing to do: it is not enabled.")
    if not apply or not st["enabled"]:
        return plan
    for argv in plan.commands:
        run(argv)
    record_state(env, {"disabledAt": int(time.time() * 1000)})
    plan.applied = True
    plan.status = status(env)
    return plan


def rollback(env: Env, apply: bool = False) -> Plan:
    st = status(env)
    plan = Plan("Rollback", status=st)
    latest = st["backups"][0] if st["backups"] else None
    src = env.backups_dir / latest if latest else None
    if not latest:
        plan.blockers.append("There is no backup of an earlier version to go back to. To stop using the plugin: disable --apply.")
    if st["state"] == "foreign":
        plan.blockers.append(f"{env.target} is not this plugin. Nothing was changed.")
    if src is not None:
        m = read_json(src / "manifest.json")
        if not isinstance(m, dict) or m.get("id") != PLUGIN_ID or not isinstance(m.get("bogen"), dict) or m["bogen"].get("plugin") != OWNER_MARK:
            plan.blockers.append(f"The backup {src} is not a copy of this plugin.")
        elif contains_link(src):
            plan.blockers.append(f"The backup {src} contains a link; it is not restored.")
    if not plan.blockers:
        plan.steps += [f"Back up {env.target}", f"Restore {src}"]
    plan.possible = not plan.blockers
    if not apply or plan.blockers:
        return plan
    target = prepared_target(env)
    staging = target.parent / f".{PLUGIN_ID}.bogen-new"
    remove_path(staging)
    shutil.copytree(src, staging, symlinks=True)
    try:
        run([env.omarchy_bin, "plugin", "validate", str(staging)])
        if exists(target):
            plan.backup = str(backup(env, target))
        publish_staging(staging, target)
    except BaseException:
        remove_path(staging)
        raise
    remove_path(src)
    record_state(env, {"rolledBackAt": int(time.time() * 1000), "restored": latest})
    plan.applied = True
    plan.status = status(env)
    return plan


def remove(env: Env, apply: bool = False) -> Plan:
    st = status(env)
    plan = Plan("Remove", status=st)
    if not st["installed"]:
        plan.blockers.append("It is not installed.")
    elif not st["installed"]["ours"]:
        plan.blockers.append(f"{env.target} is not this plugin. Nothing was changed.")
    if st["enabled"]:
        plan.blockers.append("It is enabled. Disable it first (disable --apply), so omarchy.background comes back before its files go; otherwise the desktop would have no background.")
    if not plan.blockers:
        plan.steps.append(f"Move {env.target} to {env.backups_dir}/<time>")
    plan.possible = not plan.blockers
    if not apply or plan.blockers:
        return plan
    target = prepared_target(env)
    plan.backup = str(backup(env, target))
    remove_path(target)
    record_state(env, {"removedAt": int(time.time() * 1000)})
    plan.applied = True
    plan.status = status(env)
    return plan


# ---------------------------------------------------------------- the command line


def print_plan(plan: Plan) -> None:
    head = "done" if plan.applied else "possible (plan only; add --apply)" if plan.possible else "not possible"
    lines = [f"{plan.title}: {head}"]
    lines += [f"  x {b}" for b in plan.blockers]
    lines += [f"  - {s}" for s in plan.steps]
    lines += [f"  $ {' '.join(c)}" for c in plan.commands]
    lines += [f"  note: {n}" for n in plan.notes]
    if plan.backup:
        lines.append(f"  backup: {plan.backup}")
    lines.append(f"  {plan.status.get('summary', '')}")
    print("\n".join(lines))


def print_status(st: dict, live: dict) -> None:
    inst = st["installed"]
    lines = [f"Plugin: {st['state']}{' ' + inst['version'] if inst and inst.get('version') else ''}. {st['summary']}"]
    stock = st["stock"]
    lines.append("Stock background: " + ("can be patched" if stock["compatible"] else f"cannot be patched ({stock.get('reason')})") if stock["present"] else "Stock background: not on this machine")
    if inst and inst["ours"]:
        lines.append(f"Installed by: {inst.get('installer') or 'bogen'}; derived from stock sha256 {str(inst.get('stockSha256'))[:12]}…{' (outdated)' if inst['outdated'] else ''}{'; edited: ' + ', '.join(inst['modified']) if inst['modified'] else ''}")
    for c in st["conflicts"]:
        lines.append(f"Other background clone: {c['id']}{' (enabled)' if c['enabled'] else ''} in {c['dir']}")
    if st["backups"]:
        lines.append(f"Backups: {len(st['backups'])}, newest {st['backups'][0]}")
    if "live" in live:
        lines.append(f"Running shell: {json.dumps(live['live'])}")
        stale = stale_runtime(inst.get("version") if inst else None, live["live"])
        if stale:
            lines.append(f"Next: {stale}")
    if "liveError" in live:
        lines.append(f"Running shell: {live['liveError']}")
    lines += [f"Next: {n}" for n in st["next"]]
    print("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="portrait-background", description="The Omarchy portrait background plugin. Plans unless --apply.")
    parser.add_argument("action", choices=["status", "install", "enable", "disable", "rollback", "remove"])
    parser.add_argument("--apply", action="store_true", help="make the change; without it, only say what would happen")
    parser.add_argument("--force", action="store_true", help="install: replace files you edited (a backup is kept)")
    parser.add_argument("--live", action="store_true", help="status: also ask the running shell")
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args(argv)
    if os.geteuid() == 0:
        print("portrait-background: run it as yourself, not as root: it only writes to your own config.", file=sys.stderr)
        return 2
    env = env_from()
    try:
        if args.action == "status":
            st = status(env)
            live = live_status(env) if args.live else {}
            if args.json:
                extra = {"stale": stale_runtime(st["installed"]["version"] if st["installed"] else None, live["live"])} if "live" in live else {}
                print(json.dumps({**st, **live, **extra}, indent=2))
            else:
                print_status(st, live)
            return 0
        action = {"install": lambda: install(env, args.apply, args.force), "enable": lambda: enable(env, args.apply),
                  "disable": lambda: disable(env, args.apply), "rollback": lambda: rollback(env, args.apply), "remove": lambda: remove(env, args.apply)}[args.action]
        plan = action()
    except (Refused, OSError) as e:
        print(f"portrait-background: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(plan.as_dict(), indent=2))
    else:
        print_plan(plan)
    return 0 if plan.possible else 1


if __name__ == "__main__":
    sys.exit(main())
