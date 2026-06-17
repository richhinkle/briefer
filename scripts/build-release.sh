#!/usr/bin/env bash
# Build a release tarball to hand to a friend for uploading via the console
# (Software page). The archive contains the app source only — no .venv, .git,
# config.toml, or caches — and is rebuilt fresh on the device.
#
# Usage:  ./scripts/build-release.sh [output-dir]
# Output: <output-dir>/briefer-<version>.tgz   (default output-dir: ./dist)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${1:-$ROOT/dist}"

# Version comes from the package; append a short git sha when available so two
# builds of the same version are still distinguishable.
VERSION="$(grep -oE '"[^"]+"' "$ROOT/daily_brief/__init__.py" | tr -d '"' | tail -1)"
if SHA="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null)"; then
  VERSION="${VERSION}+${SHA}"
fi

mkdir -p "$OUT_DIR"
TARBALL="$OUT_DIR/briefer-${VERSION}.tgz"

# git archive when possible (respects .gitignore, only tracked files); otherwise
# fall back to tar with explicit excludes.
if git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  git -C "$ROOT" archive --format=tar.gz --prefix="briefer/" -o "$TARBALL" HEAD
else
  tar -czf "$TARBALL" -C "$ROOT" \
    --exclude='.venv' --exclude='.git' --exclude='__pycache__' \
    --exclude='.pytest_cache' --exclude='*.pyc' --exclude='config.toml' \
    --exclude='dist' --transform='s,^\.,briefer,' .
fi

echo "built $TARBALL"
