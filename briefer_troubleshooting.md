# Briefer Troubleshooting & Install Notes

## Hardware (Pi Zero W install, August 2026)

- **Pi model:** Pi Zero W (armv7l, 32-bit) — not the Zero 2 W the docs target, but all pip wheels installed fine via piwheels.org
- **Thermal printer:** USB ID `1d81:5721` (58mm "Printer 58A"), device at `/dev/usb/lp0`
- **Button:** GPIO 24 — physical pin 18 to physical pin 14 (GND). Pin 20 had a bad solder joint; pin 14 is a reliable alternative ground nearby.
- **IP:** 192.168.1.37, hostname `brieferPi`, SSH user `rich`

## Missing apt packages

These are not in the original prerequisites but are required by Pillow:

```bash
sudo apt install -y libopenjp2-7 libfreetype6
```

Already added to `scripts/install.sh` and `INSTALL.md`.

## Config gotcha

After first boot the printer backend defaults to `dummy`. Go to **Settings** in the web UI and change it to `usb`, otherwise print jobs succeed silently but nothing comes out.
