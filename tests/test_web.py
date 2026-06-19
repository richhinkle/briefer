"""Setup web app: routes serve and edits round-trip to config.toml (offline)."""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from daily_brief.config import load_config

PASSWORD = "test-password"


def _write_config(p, with_password=True):
    pw = f'password_hash="{generate_password_hash(PASSWORD)}"\n' if with_password else ""
    p.write_text(
        '[web]\nsecret_key="testsecret"\n' + pw +
        '[location]\nlat=40.4\nlon=-3.7\ntz="Europe/Madrid"\n'
        '[[briefs]]\nname="t"\n'
        '  [[briefs.sections]]\n  type="daylight"\n  title="DAYLIGHT"\n'
        '  [[briefs.sections]]\n  type="joke"\n  enabled=false\n'
    )


@pytest.fixture
def cfgpath(tmp_path):
    p = tmp_path / "config.toml"
    _write_config(p)
    return p


def _app(cfgpath):
    from daily_brief.web import create_app

    app = create_app(cfgpath)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(cfgpath):
    """A logged-in client."""
    c = _app(cfgpath).test_client()
    c.post("/login", data={"password": PASSWORD})
    return c


def test_unauthenticated_redirects_to_login(cfgpath):
    c = _app(cfgpath).test_client()  # not logged in
    resp = c.get("/")
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]


def test_first_run_redirects_to_set_password(tmp_path):
    p = tmp_path / "config.toml"
    _write_config(p, with_password=False)
    c = _app(p).test_client()
    resp = c.get("/")
    assert resp.status_code == 302 and "/set-password" in resp.headers["Location"]


def test_wrong_password_rejected(cfgpath):
    c = _app(cfgpath).test_client()
    c.post("/login", data={"password": "nope"})
    assert c.get("/").status_code == 302  # still not authed


def test_pages_serve(client):
    for path in ("/", "/brief/t", "/settings", "/schedules", "/wifi"):
        assert client.get(path).status_code == 200


def test_preview_is_png(client):
    resp = client.get("/preview/t.png")
    assert resp.status_code == 200 and resp.mimetype == "image/png"


def test_edit_reorders_and_saves(client, cfgpath):
    resp = client.post("/brief/t", data={
        "order": "1,0",
        "sec-0-type": "daylight", "sec-0-title": "SUN", "sec-0-enabled": "on", "sec-0-icon": "sun",
        "sec-1-type": "joke", "sec-1-icon": "",
        "action": "save",
    })
    assert resp.status_code == 302
    brief = load_config(cfgpath).brief("t")
    assert [s.type for s in brief.sections] == ["joke", "daylight"]   # reordered
    daylight = brief.sections[1]
    assert daylight.title == "SUN" and daylight.options.get("icon") == "sun"
    assert brief.sections[0].enabled is False  # joke stays disabled


def test_settings_round_trip(client, cfgpath):
    client.post("/settings", data={
        "printer_backend": "usb", "usb_vendor_id": "0x1d81", "usb_product_id": "0x5721",
        "serial_port": "/dev/ttyUSB0", "serial_baudrate": "19200",
        "lat": "51.5", "lon": "-0.1", "tz": "Europe/London",
        "dot_width": "384", "body_size": "22", "heading_size": "26", "margin": "8",
        "claude_model": "claude-haiku-4-5", "ap_ssid": "brief-ap", "button_gpio": "24",
    })
    cfg = load_config(cfgpath)
    assert cfg.printer.backend == "usb"
    assert cfg.location.tz == "Europe/London"
    assert cfg.claude.model == "claude-haiku-4-5"
    assert cfg.network.ap_ssid == "brief-ap"
    assert cfg.network.button_gpio == 24


def test_software_remote_update_disabled_by_default(client, monkeypatch):
    """With the default config, the Software page won't accept an upload."""
    import io

    from daily_brief import updater

    monkeypatch.setattr(updater, "is_managed", lambda p: True)  # release-based
    monkeypatch.setattr(updater, "trigger", lambda: (_ for _ in ()).throw(
        AssertionError("trigger must not run while remote update is disabled")))

    body = client.get("/software").get_data(as_text=True)
    assert 'name="tarball"' not in body          # no upload form
    assert "disabled" in body.lower()

    resp = client.post("/software", data={"tarball": (io.BytesIO(b"x"), "r.tgz")},
                       content_type="multipart/form-data")
    assert resp.status_code == 302               # refused, redirected back


def test_software_remote_update_when_enabled(tmp_path, monkeypatch):
    """With allow_remote_update = true, a valid upload reaches the installer."""
    import io

    from werkzeug.security import generate_password_hash

    from daily_brief import updater

    p = tmp_path / "config.toml"
    p.write_text(
        f'[web]\nsecret_key="s"\npassword_hash="{generate_password_hash(PASSWORD)}"\n'
        'allow_remote_update=true\n'
        '[location]\nlat=40.4\nlon=-3.7\ntz="Europe/Madrid"\n'
        '[[briefs]]\nname="t"\n  [[briefs.sections]]\n  type="joke"\n'
    )
    calls = []
    monkeypatch.setattr(updater, "is_managed", lambda p: True)
    monkeypatch.setattr(updater, "stage_upload", lambda p, s: calls.append("stage"))
    monkeypatch.setattr(updater, "trigger", lambda: (calls.append("trigger"), (True, "ok"))[1])

    c = _app(p).test_client()
    c.post("/login", data={"password": PASSWORD})
    c.post("/software", data={"tarball": (io.BytesIO(b"x"), "r.tgz")},
           content_type="multipart/form-data")
    assert calls == ["stage", "trigger"]
