# Daily Brief

Prints a daily briefing — weather, birthdays, events, word of the day, trivia,
"on this day", a joke — on a 58mm ESC/POS thermal printer attached to a Raspberry
Pi Zero (2) W. Driven by [python-escpos](https://github.com/python-escpos/python-escpos).
The brief is rendered as a bitmap with a TrueType font, so it can show weather
pictograms, checkboxes, and thin rules.

## How it works

Runs as an appliance: a password-protected **web console** edits everything,
**briefs** (named, ordered sets of sections) are fired by **schedules**, and a
daemon prints them. An offline or misconfigured source prints "(unavailable)"
instead of failing the brief.

- **Model:** section → brief → schedule, all in one `config.toml`.
- **Console:** reorder sections (drag-drop), edit keys / calendar URLs / prompts,
  manage briefs + schedules + settings, enter WiFi, print/preview.
- **Setup AP:** with no WiFi the Pi becomes an access point to reach the console
  and join a network; it drops once online. A GPIO button re-opens it.
  (Bookworm + NetworkManager.)

Sections: `greeting`, `weather` (OpenWeatherMap), `birthdays` / `events` /
`oncall` (iCal), `word`, `trivia`, `onthisday`, `daylight`, `joke`, `ascii`,
`ai` (your prompt → Claude), and `iss` / `moon` / `planets`.

## Project layout

```
daily_brief/            Python package
  __main__.py           print CLI: build + print a brief (--brief, --dry-run, --out)
  daemon.py             long-running service: scheduler + setup-mode state machine
  config.py             load/save config.toml; briefs/schedules/globals dataclasses
  printer.py            make_printer() — the only place that touches hardware
  brief.py              Brief/Section/Item data model + build_brief(config, brief)
  render.py             draws the brief to a bitmap and prints it as an image
  network.py            nmcli wrapper (AP / WiFi / connectivity); no-ops off-Pi
  sources/              one builder per section + specs.py (field schema for the UI)
  web/                  Flask setup UI (templates, static, forms)
  assets/               bundled fonts + weather/header pictograms + ISS world map
scripts/                install.sh, printer_test.py, build-release.sh, sync-to-pi.sh
systemd/                daily-brief.service + the release-updater unit
config.example.toml     copy to config.toml (or let the web UI write it)
```

## Develop on a laptop (no printer)

Requires Python 3.11+. The `dummy` backend needs no hardware.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.toml config.toml           # then edit it

python -m daily_brief --dry-run              # render a brief to preview.png
python -m daily_brief.web                     # console at http://127.0.0.1:8080
python -m daily_brief.daemon --no-setup       # scheduler only (laptop-safe)
pytest
```

## Run on the Pi

```bash
sudo ./scripts/install.sh
```

Installs the daemon to run **unprivileged** as a dedicated `daily-brief` user.
First boot with no WiFi: join the `daily-brief-setup` AP → open
`http://10.42.0.1` → set a password → enter WiFi. Afterward the console is at
`http://<hostname>.local`. Full walkthrough: **[INSTALL.md](INSTALL.md)**.

## Printer setup

1. Find how it connects:
   ```bash
   python scripts/printer_test.py --list-usb     # raw USB → note vendor:product
   ls -l /dev/ttyUSB* /dev/serial* 2>/dev/null   # serial → note the port
   ```
   (Ignore `1d6b:xxxx` — that's the Pi's internal USB hub.)
2. Set `[printer.usb]` (vendor_id / product_id) or `[printer.serial]` (port /
   baudrate) in `config.toml`, and `backend` to match.
3. Test — prints a page exercising alignment, styles, a ruler, and a QR code:
   ```bash
   python scripts/printer_test.py --backend usb   # or: --backend serial
   ```

Raw-USB permission error on Linux? Add a udev rule (your IDs):

```bash
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="1d81", ATTRS{idProduct}=="5721", GROUP="plugdev", MODE="0660"' \
  | sudo tee /etc/udev/rules.d/99-escpos.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## Configuration

All settings live in `config.toml` (gitignored); start from
[`config.example.toml`](config.example.toml).

- `printer.backend` = `dummy` | `usb` | `serial`
- `[location]` — `lat` / `lon` / `tz` (used by `weather`, `daylight`)
- `[render]` — width (`dot_width = 384` for 58mm), font, text sizes
- Sections — file order is print order; `enabled = false` skips one; extra keys
  pass to that source (`api_key`, `ical_url`, …)

Only two sources need credentials; everything else works out of the box:

- **`weather`** — free [OpenWeatherMap](https://openweathermap.org/api) `api_key`
- **`birthdays` / `events` / `oncall`** — a published iCal `.ics` URL (`webcal://` ok)
- **AI (Claude)** — `[claude] enabled` + an `api_key`; used by `greeting`,
  `word`, `ai`, and `ascii` (each with `use_claude = true`). On failure those
  print "(AI unavailable)"; off or unkeyed falls back to local behavior. Defaults
  to Opus; set `model = "claude-haiku-4-5"` for ~5× lower cost.
