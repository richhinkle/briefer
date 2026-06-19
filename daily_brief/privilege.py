"""Run the few commands that still need privilege, without being root.

The daemon runs as an unprivileged ``daily-brief`` user (see
``scripts/install.sh`` and ``systemd/daily-brief.service``). Almost everything
works from that account through group membership — ``nmcli`` (netdev), GPIO
(gpio), the printer (dialout/plugdev) — and it binds port 80 via
``AmbientCapabilities``. Two actions can't be granted that way: powering the Pi
off (button hold) and restarting the systemd service (self-update). An
``/etc/sudoers.d/daily-brief`` drop-in grants NOPASSWD on exactly those commands;
:func:`sudo_wrap` prefixes ``sudo -n`` so the calls go through it.

When already running as root (a legacy root install, or off-Pi tests where the
commands are skipped anyway) :func:`sudo_wrap` is a no-op, so nothing regresses.
"""

from __future__ import annotations

import os


def sudo_wrap(args: list[str]) -> list[str]:
    """Return ``args`` prefixed with ``sudo -n`` unless we're already root.

    ``-n`` (non-interactive) makes a missing/incorrect sudoers grant fail fast
    instead of blocking on a password prompt the daemon could never answer.
    """
    if getattr(os, "geteuid", lambda: 0)() == 0:
        return list(args)
    return ["sudo", "-n", *args]
