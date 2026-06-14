# Daily Brief

Print a daily morning briefing — weather, birthdays, upcoming events, a word of
the day, trivia, an "on this day" fact, and a dad joke — on a thermal receipt
printer attached to a Raspberry Pi Zero W or Zero 2 W.

The printer is an ESC/POS receipt module (USB/serial) driven by
[python-escpos](https://github.com/python-escpos/python-escpos). Paper is 58mm.
The brief is drawn as a bitmap with a modern TrueType font (not the built-in
receipt font), so it can show weather pictograms, birthday checkboxes, and thin
section rules.

## Status

Working. It runs as a small appliance: a **setup-mode web UI** edits everything,
multiple **briefs** (named, ordered sets of sections) are fired by **schedules**,
and a daemon prints them at their times. Sources degrade gracefully: one that's
offline or misconfigured prints "(unavailable)" instead of failing the brief.

- **Data model:** section (a content block) → brief (an ordered set) → schedule
  (prints a brief at a time). All in one `config.toml`.
- **Web console (always on, password-protected):** reorder sections (drag-drop),
  edit keys / calendar URLs / prompts, manage briefs + schedules + global
  settings, enter WiFi, and print/preview. You set the password on first visit.
- **Setup access point:** on boot with no WiFi the Pi becomes an access point so
  you can reach the console and join a network; the AP drops once it's online. A
  GPIO button re-opens it to change WiFi. (Bookworm + NetworkManager.)

Built-in sections: `greeting` (the configurable header), `weather`
(OpenWeatherMap), `birthdays` + `events` (iCal), `oncall` (iCal), `word`
(rare/SAT word + Free Dictionary), `trivia`, `onthisday`, `daylight`, `joke`,
`ascii` (a daily ASCII-art doodle), `ai` (your own prompt → Claude), and space:
`iss`, `moon`, `planets`. The birthdays header gets a small icon (opt others in
with `icon = "<key>"`).

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
scripts/                printer_test.py, gen_icons.py, gen_weather_icons.py, sync-to-pi.sh
systemd/daily-brief.service   runs the daemon on boot
tests/                  pytest (dummy backend / Flask test client — no hardware)
config.example.toml     copy to config.toml (or let the web UI write it)
requirements.txt
```

## Setup mode, briefs & schedules

```bash
python -m daily_brief.web                 # setup UI at http://127.0.0.1:8080 (dev)
python -m daily_brief --brief morning --dry-run   # preview one brief to preview.png
python -m daily_brief.daemon --no-setup   # run just the scheduler (laptop-safe)
```

On the Pi the daemon runs via systemd and handles the access point, web server,
and button automatically:

```bash
sudo apt install python3-gpiozero python3-lgpio   # optional: the setup button
sudo cp systemd/daily-brief.service /etc/systemd/system/
sudo systemctl enable --now daily-brief
```

First boot with no WiFi → join the `daily-brief-setup` access point → browse to
`http://10.42.0.1` → set a console password → enter your WiFi. The device joins
the network (the AP drops) and the console stays reachable on your LAN at the
Pi's address. Press the button to re-open the AP to change WiFi.

> **Full Pi setup from a clean OS install:** see **[INSTALL.md](INSTALL.md)**.

## Setup

Works on macOS (for development, using the `dummy` backend) and on the Pi (with
the real printer). Requires Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.toml config.toml      # then edit config.toml
```

On the Pi, the USB backend also needs libusb:

```bash
sudo apt install libusb-1.0-0
```

## Develop on your laptop (no printer)

`--dry-run` renders the brief to a PNG (no printer needed) so you can preview the
exact layout:

```bash
python -m daily_brief --dry-run             # writes preview.png
python -m daily_brief --dry-run --out /tmp/brief.png
python scripts/printer_test.py --backend dummy
pytest                                      # tests use the dummy backend
```

## Bring up the printer on the Pi

1. **Find out how it connects.** These cheap modules are either raw USB ESC/POS
   devices or a USB-serial adapter.

   ```bash
   python scripts/printer_test.py --list-usb     # raw USB? note vendor:product
   ls -l /dev/ttyUSB* /dev/serial* 2>/dev/null   # serial? note the port
   ```

   > Ignore `1d6b:xxxx` entries — that's the Pi's internal USB root hub, not the
   > printer.

2. **Put the details in `config.toml`** — either `[printer.usb]` (vendor_id /
   product_id) or `[printer.serial]` (port / baudrate), and set `backend`
   accordingly.

3. **Print the test page:**

   ```bash
   python scripts/printer_test.py --backend usb      # or: --backend serial
   ```

   You should get a receipt exercising alignment, bold/underline, double
   size, a width ruler, and a QR code. If that looks right, the hardware is good.

4. **Print the brief:**

   ```bash
   python -m daily_brief --backend usb     # or set backend in config.toml
   ```

### USB permissions on Linux

If the USB backend fails with a permission/access error, add a udev rule so you
don't need sudo (replace the IDs with yours):

```bash
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="1d81", ATTRS{idProduct}=="5721", MODE="0666"' \
  | sudo tee /etc/udev/rules.d/99-escpos.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## Configuration

All settings live in `config.toml` (gitignored). Start from
[`config.example.toml`](config.example.toml).

- `printer.backend` = `dummy` | `usb` | `serial`.
- `[location]` — `lat` / `lon` / `tz`, used by `weather` and `daylight`.
- `[render]` — bitmap width (`dot_width = 384` for 58mm), font, text sizes.
- `[[sections]]` — one block per section. **File order is print order**; set
  `enabled = false` to skip one. Each block's extra keys are passed to that
  source (e.g. `api_key` for weather, `ical_url` for birthdays/events).

### API keys / setup per section

Only two sections need credentials; everything else works out of the box:

- **`weather`** — free [OpenWeatherMap](https://openweathermap.org/api) `api_key`.
- **`birthdays` / `events` / `oncall`** — a published iCal `.ics` URL (e.g. a
  Google Calendar "secret address"; `webcal://` URLs are accepted).
- **`iss`, `moon`, `planets`, `word`, `trivia`, `onthisday`, `daylight`, `joke`,
  `ascii`** — no key needed.
- **AI (Claude)** — `[claude] enabled` is a master toggle (a checkbox in
  Settings). When it's on **and** an `api_key` is set, AI is used by the
  **greeting**, **word of the day**, the **`ai`** section, and **ASCII art**
  (`use_claude = true`). If a call fails, those sections print **"(AI
  unavailable)"** rather than quietly using the local version — so a broken key
  is visible. Turn the toggle off (or leave the key unset) and everything uses
  its local behavior (rotating greeting, Free Dictionary, the bundled gallery).
  Defaults to Opus; set `model = "claude-haiku-4-5"` for ~5× lower cost.
