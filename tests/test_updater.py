"""The upload updater: atomic install, smoke-test gate, and auto-rollback.

The heavy/host-specific steps (venv build, smoke render, systemctl, the HTTP
health check) are stubbed; the logic under test is the staging, the safe
extraction, the symlink flip, and the rollback decision.
"""

from __future__ import annotations

import io
import tarfile

import pytest

from daily_brief import updater


def _make_tarball(path, version="9.9.9", wrap="briefer", extra=None):
    """A minimal release archive containing a daily_brief package."""
    path.parent.mkdir(parents=True, exist_ok=True)
    init = f'__version__ = "{version}"\n'.encode()
    with tarfile.open(path, "w:gz") as tar:
        def add(name, data):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        prefix = f"{wrap}/" if wrap else ""
        add(f"{prefix}daily_brief/__init__.py", init)
        add(f"{prefix}requirements.txt", b"")
        if extra:
            extra(tar, prefix)


@pytest.fixture
def layout(tmp_path):
    """A release-based install with one existing ('previous') release live."""
    base = tmp_path
    (base / "config.toml").write_text('[web]\nport = 80\n')
    prev = base / "releases" / "0.0.1-old"
    (prev / "daily_brief").mkdir(parents=True)
    (prev / "daily_brief" / "__init__.py").write_text('__version__ = "0.0.1"\n')
    (base / "current").symlink_to(prev)
    return updater.paths_for(base / "config.toml")


@pytest.fixture
def no_host(monkeypatch):
    """Stub the host-specific steps so apply_pending runs anywhere."""
    monkeypatch.setattr(updater, "_build_venv", lambda rel: (rel / ".venv").mkdir())
    monkeypatch.setattr(updater, "_systemctl", lambda *a: None)
    monkeypatch.setattr(updater, "_smoke_test", lambda rel, cfg: True)
    monkeypatch.setattr(updater, "_healthy", lambda p: True)


def test_paths_and_managed(layout, tmp_path):
    assert layout.base == tmp_path
    assert updater.is_managed(layout) is True
    # a plain checkout (no `current` symlink) is not managed
    plain = updater.paths_for(tmp_path / "elsewhere" / "config.toml")
    assert updater.is_managed(plain) is False


def test_stage_upload_is_atomic(layout):
    updater.stage_upload(layout, io.BytesIO(b"hello"))
    assert layout.pending.read_bytes() == b"hello"
    assert not (layout.staging / "pending.part").exists()


def test_find_package_root_handles_wrapper(tmp_path):
    wrapped = tmp_path / "w"
    (wrapped / "top" / "daily_brief").mkdir(parents=True)
    (wrapped / "top" / "daily_brief" / "__init__.py").write_text("")
    assert updater._find_package_root(wrapped) == wrapped / "top"

    flat = tmp_path / "f"
    (flat / "daily_brief").mkdir(parents=True)
    (flat / "daily_brief" / "__init__.py").write_text("")
    assert updater._find_package_root(flat) == flat


def test_safe_extract_rejects_traversal(tmp_path):
    bad = tmp_path / "bad.tgz"
    with tarfile.open(bad, "w:gz") as tar:
        info = tarfile.TarInfo("../escape.txt")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    with tarfile.open(bad, "r:*") as tar:
        with pytest.raises(ValueError):
            updater._safe_extract(tar, tmp_path / "dest")


def test_apply_success_flips_and_records(layout, no_host):
    _make_tarball(layout.pending, version="9.9.9")
    assert updater.apply_pending(layout) == 0

    assert layout.current.resolve().name.startswith("9.9.9-")
    assert updater.read_status(layout)["result"] == "success"
    assert not layout.pending.exists()  # consumed


def test_apply_rolls_back_when_unhealthy(layout, no_host, monkeypatch):
    monkeypatch.setattr(updater, "_healthy", lambda p: False)
    previous = layout.current.resolve()
    _make_tarball(layout.pending, version="9.9.9")

    assert updater.apply_pending(layout) == 1
    assert layout.current.resolve() == previous  # rolled back
    assert updater.read_status(layout)["result"] == "rolled_back"
    assert not layout.pending.exists()


def test_apply_keeps_current_when_smoke_fails(layout, no_host, monkeypatch):
    monkeypatch.setattr(updater, "_smoke_test", lambda rel, cfg: False)
    previous = layout.current.resolve()
    _make_tarball(layout.pending, version="9.9.9")

    assert updater.apply_pending(layout) == 1
    assert layout.current.resolve() == previous  # never flipped
    assert updater.read_status(layout)["result"] == "failed"


def test_apply_noop_without_pending(layout, no_host):
    assert updater.apply_pending(layout) == 0
    assert updater.read_status(layout) == {}  # nothing recorded
