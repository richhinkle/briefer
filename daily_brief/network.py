"""NetworkManager (`nmcli`) wrapper for setup mode.

Bookworm ships NetworkManager, which can create a WiFi hotspot and join networks
with a few `nmcli` calls. Everything here degrades safely: if `nmcli` isn't
present (e.g. on a laptop) `available()` is False and the daemon skips setup
mode entirely, just running the scheduler.

The daemon must run as root for these to work (AP + connection changes).
"""

from __future__ import annotations

import logging
import shutil
import subprocess

log = logging.getLogger("daily_brief.network")

HOTSPOT_CON = "Hotspot"  # connection name nmcli uses for `wifi hotspot`


def available() -> bool:
    """True if nmcli exists — i.e. we're on a NetworkManager system (the Pi)."""
    return shutil.which("nmcli") is not None


def _run(args: list[str], timeout: float = 20.0) -> tuple[int, str]:
    """Run `nmcli args...`; return (returncode, stdout). (-1, "") on error."""
    try:
        proc = subprocess.run(
            ["nmcli", *args], capture_output=True, text=True, timeout=timeout
        )
        if proc.returncode != 0:
            log.warning("nmcli %s failed: %s", " ".join(args), proc.stderr.strip())
        return proc.returncode, proc.stdout
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("nmcli %s errored: %s", " ".join(args), exc)
        return -1, ""


def is_online() -> bool:
    """True when NetworkManager reports full connectivity."""
    if not available():
        return False
    rc, out = _run(["-t", "-f", "CONNECTIVITY", "general", "status"], timeout=8)
    return rc == 0 and out.strip() == "full"


def current_ssid() -> str | None:
    """SSID of the active WiFi connection, or None."""
    rc, out = _run(["-t", "-f", "ACTIVE,SSID", "dev", "wifi"], timeout=8)
    if rc != 0:
        return None
    for line in out.splitlines():
        if line.startswith("yes:"):
            return line.split(":", 1)[1] or None
    return None


def scan() -> list[dict]:
    """Nearby networks as [{ssid, signal, secure}], strongest first, deduped."""
    _run(["dev", "wifi", "rescan"], timeout=15)  # best-effort refresh
    rc, out = _run(["-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi"], timeout=15)
    if rc != 0:
        return []
    best: dict[str, dict] = {}
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) < 3 or not parts[0]:
            continue
        ssid = parts[0]
        try:
            signal = int(parts[1])
        except ValueError:
            signal = 0
        secure = parts[2] not in ("", "--", "none")
        if ssid not in best or signal > best[ssid]["signal"]:
            best[ssid] = {"ssid": ssid, "signal": signal, "secure": secure}
    return sorted(best.values(), key=lambda d: d["signal"], reverse=True)


def connect(ssid: str, password: str | None) -> tuple[bool, str]:
    """Join a WiFi network. Returns (ok, message)."""
    args = ["dev", "wifi", "connect", ssid]
    if password:
        args += ["password", password]
    rc, _ = _run(args, timeout=45)
    if rc == 0:
        return True, f"Connected to {ssid}."
    return False, f"Could not connect to {ssid} (check the password)."


def start_ap(ssid: str, password: str) -> bool:
    """Bring up the setup access point. Takes the radio offline (single radio)."""
    rc, _ = _run(["dev", "wifi", "hotspot", "ssid", ssid, "password", password], timeout=30)
    return rc == 0


def stop_ap() -> None:
    """Tear the hotspot down (ignored if it isn't up)."""
    _run(["connection", "down", HOTSPOT_CON], timeout=15)
