#!/usr/bin/env bash
# One-time migration: convert a plain checkout into the release-based layout the
# console's Software updater expects. Run this ON THE PI, once.
#
#   from a checkout at /home/briefer/briefer it produces:
#     /home/briefer/config.toml          (moved out of the checkout)
#     /home/briefer/releases/<version>/  (a fresh copy + venv)
#     /home/briefer/current -> releases/<version>
#     /home/briefer/staging/
#
# Usage (on the Pi):  sudo -u briefer ./scripts/setup-releases.sh
# Re-run is safe: it builds a new release and re-points `current`.

set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"     # the checkout this script lives in
BASE="$(dirname "$SRC")"                      # e.g. /home/briefer
RELEASES="$BASE/releases"
STAGING="$BASE/staging"

VERSION="$(grep -oE '"[^"]+"' "$SRC/daily_brief/__init__.py" | tr -d '"' | tail -1)"
STAMP="$(date +%Y%m%d-%H%M%S)"
REL="$RELEASES/$VERSION-$STAMP"

echo "==> install base: $BASE"
echo "==> new release:  $REL"

mkdir -p "$RELEASES" "$STAGING"

# Copy source (tracked files only — no venv, git, config, or caches).
echo "==> copying source"
rsync -a \
  --exclude='.venv' --exclude='.git' --exclude='__pycache__' \
  --exclude='.pytest_cache' --exclude='*.pyc' --exclude='config.toml' \
  --exclude='dist' --exclude='releases' --exclude='staging' \
  "$SRC/" "$REL/"

# Fresh venv (a moved venv would have stale hardcoded paths).
echo "==> building venv (this can take a few minutes on a Pi Zero)"
python3 -m venv --system-site-packages "$REL/.venv"
"$REL/.venv/bin/pip" install -r "$REL/requirements.txt"

# Move config out of the checkout so updates never touch it.
if [ -f "$SRC/config.toml" ] && [ ! -f "$BASE/config.toml" ]; then
  echo "==> moving config.toml to $BASE/config.toml"
  mv "$SRC/config.toml" "$BASE/config.toml"
fi

# Point current at the new release (atomic replace via -T -f -n).
ln -sfnT "$REL" "$BASE/current"
echo "==> current -> $(readlink "$BASE/current")"

cat <<EOF

Done. Now install/refresh the systemd units (as root):

  sudo cp $REL/systemd/daily-brief.service        /etc/systemd/system/
  sudo cp $REL/systemd/daily-brief-update.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl restart daily-brief

The units already point at $BASE/current and $BASE/config.toml.
After this, update the device from the console's Software page — no SSH needed.
EOF
