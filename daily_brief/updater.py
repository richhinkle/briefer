"""Foolproof software update: install an uploaded tarball, atomically.

The console (web UI) lets an authorized user upload a new release as a `.tgz`.
Installing code that restarts the daemon can't be done inside the web request
(the restart would kill it mid-flight), and a bad build must never be able to
brick a device. So the flow is deliberately split and defensive:

    web upload  ->  staging/pending.tgz
    systemctl start daily-brief-update   (a *separate* oneshot unit)
    daily_brief.updater apply            (this module)

`apply_pending()` never touches the running install in place. It unpacks the
tarball into a fresh `releases/<version>/`, builds its venv, and **smoke-tests
it** before going live; only then does it flip the `current` symlink and restart
the service. After the restart it **health-checks** the console and, if the new
version doesn't come up, flips the symlink back to the previous release — so a
broken upload self-heals to the last working version.

Because the unit runs `current/.venv/.../daily_brief.updater` (the *old* code)
to perform the apply, even a hopelessly broken new build can't break the
mechanism that recovers from it.

Layout (anchored on the directory holding config.toml, e.g. /home/briefer):

    <base>/
      config.toml            # outside releases; never touched by updates
      current -> releases/<version>
      releases/<version>/    # code + .venv per version
      staging/pending.tgz    # the most recent upload, consumed on apply
      update-status.json      # last result, surfaced in the console
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

log = logging.getLogger("daily_brief.updater")

SERVICE = "daily-brief"
KEEP_RELEASES = 3  # how many old releases to retain for rollback / debugging
HEALTH_TIMEOUT = 45  # seconds to wait for the restarted console to answer


@dataclass
class Paths:
    base: Path
    config: Path

    @property
    def releases(self) -> Path:
        return self.base / "releases"

    @property
    def current(self) -> Path:
        return self.base / "current"

    @property
    def staging(self) -> Path:
        return self.base / "staging"

    @property
    def pending(self) -> Path:
        return self.staging / "pending.tgz"

    @property
    def status_file(self) -> Path:
        return self.base / "update-status.json"


def paths_for(config_path: str | os.PathLike) -> Paths:
    """Derive the release layout from the config file's location.

    The config lives *outside* the swappable releases, so its parent is the
    stable install base that holds `current`, `releases/`, and `staging/`.
    """
    config = Path(config_path).resolve()
    return Paths(base=config.parent, config=config)


def is_managed(p: Paths) -> bool:
    """True only on a release-based install (a `current` symlink exists).

    A plain dev checkout or a non-restructured install returns False, so the
    console can hide the upload form rather than fail confusingly.
    """
    return p.current.is_symlink()


def current_version() -> str:
    from . import __version__

    return __version__


# --- status, surfaced in the console ---------------------------------------


def read_status(p: Paths) -> dict:
    try:
        return json.loads(p.status_file.read_text())
    except (OSError, ValueError):
        return {}


def _write_status(p: Paths, result: str, message: str, version: str | None = None) -> None:
    payload = {
        "result": result,  # "success" | "failed" | "rolled_back" | "running"
        "message": message,
        "version": version,
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    try:
        p.status_file.write_text(json.dumps(payload, indent=2))
    except OSError as exc:
        log.warning("could not write status: %s", exc)


# --- upload + trigger (called from the web app) ----------------------------


def stage_upload(p: Paths, fileobj) -> None:
    """Save an uploaded tarball as the pending update (atomic rename)."""
    p.staging.mkdir(parents=True, exist_ok=True)
    tmp = p.staging / "pending.part"
    with open(tmp, "wb") as out:
        shutil.copyfileobj(fileobj, out)
    os.replace(tmp, p.pending)


def trigger() -> tuple[bool, str]:
    """Kick off the separate oneshot updater unit so it survives the restart."""
    if not shutil.which("systemctl"):
        return False, "systemctl unavailable (not a Pi/systemd install)."
    try:
        subprocess.run(
            ["systemctl", "start", "--no-block", f"{SERVICE}-update.service"],
            check=True,
        )
        return True, "Update started."
    except (subprocess.CalledProcessError, OSError) as exc:
        return False, f"Could not start updater: {exc}"


# --- the apply, run by the oneshot unit ------------------------------------


def _systemctl(*args: str) -> None:
    if shutil.which("systemctl"):
        subprocess.run(["systemctl", *args], check=False)
    else:
        log.info("(no systemctl) would run: systemctl %s", " ".join(args))


def _service_active() -> bool:
    if not shutil.which("systemctl"):
        return True  # nothing to check off-Pi
    r = subprocess.run(
        ["systemctl", "is-active", SERVICE], capture_output=True, text=True
    )
    return r.stdout.strip() == "active"


def _console_port(p: Paths) -> int:
    """Best-effort read of the console port for the health check."""
    try:
        import tomllib

        data = tomllib.loads(p.config.read_text())
        return int(data.get("web", {}).get("port", 80))
    except Exception:
        return 80


def _healthy(p: Paths) -> bool:
    """Wait for the restarted daemon: service active + console answering."""
    port = _console_port(p)
    url = f"http://127.0.0.1:{port}/login"
    deadline = time.monotonic() + HEALTH_TIMEOUT
    while time.monotonic() < deadline:
        time.sleep(2)
        if not _service_active():
            continue
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.status in (200, 302, 303):
                    return True
        except Exception:
            pass
    return False


def _find_package_root(extracted: Path) -> Path | None:
    """Locate the dir containing the `daily_brief/` package in an extraction.

    Tolerates tarballs that wrap everything in a single top-level directory.
    """
    if (extracted / "daily_brief" / "__init__.py").exists():
        return extracted
    children = [c for c in extracted.iterdir() if c.is_dir()]
    if len(children) == 1 and (children[0] / "daily_brief" / "__init__.py").exists():
        return children[0]
    return None


def _extracted_version(root: Path) -> str:
    init = root / "daily_brief" / "__init__.py"
    try:
        for line in init.read_text().splitlines():
            if line.strip().startswith("__version__"):
                return line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return "unknown"


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    """Extract, rejecting members that would escape the destination dir."""
    dest = dest.resolve()
    for member in tar.getmembers():
        target = (dest / member.name).resolve()
        if not str(target).startswith(str(dest) + os.sep) and target != dest:
            raise ValueError(f"unsafe path in tarball: {member.name!r}")
        if member.issym() or member.islnk():
            raise ValueError(f"links not allowed in tarball: {member.name!r}")
    try:
        tar.extractall(dest, filter="data")  # py>=3.12; rejects unsafe members
    except TypeError:
        tar.extractall(dest)  # older Python; our checks above already guard


def _build_venv(release: Path) -> None:
    """Create the release's venv and install its requirements."""
    venv = release / ".venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--system-site-packages", str(venv)],
        check=True,
    )
    pip = venv / "bin" / "pip"
    req = release / "requirements.txt"
    if req.exists():
        subprocess.run([str(pip), "install", "-r", str(req)], check=True)


def _smoke_test(release: Path, config: Path) -> bool:
    """Render a brief with the new code against the live config (read-only).

    Exercises the friend's *actual* setup, so a release that breaks on their
    specific briefs/sources is caught before it ever goes live.
    """
    py = release / ".venv" / "bin" / "python"
    out = release / ".smoke.png"
    r = subprocess.run(
        [str(py), "-m", "daily_brief", "--dry-run", "--config", str(config),
         "--out", str(out)],
        capture_output=True, text=True, cwd=str(release),
    )
    if r.returncode != 0:
        log.error("smoke test failed: %s", (r.stderr or r.stdout).strip())
    return r.returncode == 0


def _flip(current: Path, target: Path) -> None:
    """Atomically point `current` at `target` (symlink swap via rename)."""
    tmp = current.with_name("current.new")
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(target)
    os.replace(tmp, current)  # atomic on POSIX, even over an existing symlink


def _prune(p: Paths, protect: set[Path]) -> None:
    if not p.releases.is_dir():
        return
    rels = sorted(
        (d for d in p.releases.iterdir() if d.is_dir() and not d.name.startswith(".")),
        key=lambda d: d.stat().st_mtime,
    )
    keep = set(protect)
    for d in rels[-KEEP_RELEASES:]:
        keep.add(d.resolve())
    for d in rels:
        if d.resolve() not in keep:
            shutil.rmtree(d, ignore_errors=True)


def apply_pending(p: Paths) -> int:
    """Install staging/pending.tgz with smoke test, atomic flip, and rollback.

    Returns a process exit code (0 on success or nothing-to-do).
    """
    if not p.pending.exists():
        log.info("no pending update")
        return 0
    if not is_managed(p):
        _write_status(p, "failed", "Not a release-based install; cannot update.")
        return 1

    previous = p.current.resolve()
    _write_status(p, "running", "Installing uploaded update…")

    p.releases.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".unpack-", dir=p.releases))
    new_release: Path | None = None
    try:
        with tarfile.open(p.pending, "r:*") as tar:
            _safe_extract(tar, work)

        root = _find_package_root(work)
        if root is None:
            _write_status(p, "failed", "Tarball has no daily_brief/ package.")
            return 1

        version = _extracted_version(root)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        new_release = p.releases / f"{version}-{stamp}"
        shutil.move(str(root), str(new_release))

        log.info("building venv for %s", new_release.name)
        _build_venv(new_release)

        log.info("smoke-testing %s", new_release.name)
        if not _smoke_test(new_release, p.config):
            _write_status(p, "failed", f"Smoke test failed for {version}; kept current.",
                          version=version)
            return 1

        log.info("activating %s", new_release.name)
        _flip(p.current, new_release)
        _systemctl("restart", SERVICE)

        if _healthy(p):
            _write_status(p, "success", f"Updated to {version}.", version=version)
            _prune(p, protect={new_release.resolve(), previous})
            p.pending.unlink(missing_ok=True)
            return 0

        # New version won't come up — roll back to the last working release.
        log.error("health check failed; rolling back to %s", previous.name)
        _flip(p.current, previous)
        _systemctl("restart", SERVICE)
        _write_status(p, "rolled_back",
                      f"{version} failed to start; rolled back to {previous.name}.",
                      version=version)
        return 1
    except Exception as exc:
        log.exception("update failed")
        _write_status(p, "failed", f"Update error: {exc}")
        # Make sure we're still pointing at something that works.
        if p.current.resolve() != previous and previous.exists():
            _flip(p.current, previous)
            _systemctl("restart", SERVICE)
        return 1
    finally:
        shutil.rmtree(work, ignore_errors=True)
        # On any non-success path, drop the pending tarball so we don't loop.
        p.pending.unlink(missing_ok=True)
        if new_release is not None and p.current.resolve() != new_release.resolve():
            shutil.rmtree(new_release, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="daily_brief.updater",
        description="Install the pending uploaded release (atomic, with rollback).",
    )
    parser.add_argument(
        "--config", required=True,
        help="Path to config.toml; its directory is the install base.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return apply_pending(paths_for(args.config))


if __name__ == "__main__":
    raise SystemExit(main())
