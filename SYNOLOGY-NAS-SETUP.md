# Thermal Printer on Synology NAS (Docker)

Guide for running applications that use a USB thermal/POS receipt printer inside a Docker container on a Synology NAS.

## Hardware

- **NAS:** Synology DiskStation (DSM with Docker/Container Manager)
- **Printer:** Rongta POS thermal receipt printer (80mm, ESC/POS compatible)
- **Connection:** USB — the printer connects via a USB cable to the NAS and is managed by the Linux `usblp` kernel driver, which creates `/dev/usb/lp0`

## Key Discovery: USB Printer Access in Docker

The Linux `usblp` kernel driver claims the USB printer and exposes it as `/dev/usb/lp0`. This means:

- **`pyusb` / raw USB access does NOT work** — the kernel driver already owns the device, so `python-escpos`'s `Usb` backend fails with `[Errno 19] No such device`
- **File-based access DOES work** — writing directly to `/dev/usb/lp0` (either raw bytes or via `python-escpos`'s `File` backend) works perfectly

### What works

```python
# python-escpos File backend
from escpos.printer import File
p = File("/dev/usb/lp0")
p.text("Hello!")
p.cut()
p.close()
```

```python
# Raw ESC/POS (no library needed)
with open("/dev/usb/lp0", "wb") as p:
    p.write(b"\x1b\x40")           # initialize
    p.write(b"Hello!\n")           # text
    p.write(b"\x1d\x56\x00")      # cut
```

### What does NOT work

```python
# python-escpos Usb backend — FAILS
from escpos.printer import Usb
p = Usb(0x0fe6, 0x811e)  # DeviceNotFoundError: [Errno 19]
```

## Printer USB Identity

| Field | Value |
|-------|-------|
| Vendor ID | `0fe6` |
| Product ID | `811e` |
| Device path | `/dev/usb/lp0` |
| Description | Likely a USB-to-parallel adapter (GD2078A8272D81735) |

To identify your printer, unplug it and compare `lsusb` output before/after.

## Docker Setup

### docker-compose.yml

```yaml
version: "3.8"

services:
  your-app:
    build: .
    container_name: your-app
    restart: unless-stopped

    # Pass through the USB printer device
    devices:
      - /dev/usb/lp0:/dev/usb/lp0

    # If your app has a web UI
    ports:
      - "8080:80"

    volumes:
      - ./data:/app/data
```

### Key points

1. **Device passthrough:** `devices: ["/dev/usb/lp0:/dev/usb/lp0"]` gives the container access to the printer
2. **Don't mount single files** — if your app does atomic writes (write `.tmp` then `rename()`), mount a **directory** instead. Single-file bind mounts fail with `[Errno 16] Device or resource busy` on rename
3. **Verify inside container:** `ls -la /dev/usb/lp0` should show `crw-rw---- 1 root lp 180, 0`

### Dockerfile essentials

```dockerfile
FROM python:3.11-slim

# Required for python-escpos + Pillow (image rendering)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libusb-1.0-0 \
    libjpeg62-turbo \
    libfreetype6 \
    libopenjp2-7 \
    && rm -rf /var/lib/apt/lists/*

# If using python-escpos
RUN pip install python-escpos>=3.0
```

## python-escpos Configuration

If your app uses `python-escpos` with a config file:

```toml
[printer]
backend = "file"

[printer.serial]
port = "/dev/usb/lp0"
```

The `File` backend is the correct choice — it opens the device path and writes bytes directly, same as the kernel driver expects.

## Quick Validation

After `docker compose up -d`, verify the printer works:

```bash
# Check device is accessible
docker exec your-app ls -la /dev/usb/lp0

# Test print
docker exec your-app python -c 'from escpos.printer import File; p = File("/dev/usb/lp0"); p.text("Hello from Docker!"); p.cut(); p.close()'
```

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `DeviceNotFoundError: [Errno 19]` | Using `Usb` backend; kernel driver owns device | Switch to `File` backend with `/dev/usb/lp0` |
| `[Errno 16] Device or resource busy` on config write | Single-file Docker bind mount | Mount a directory instead of a file |
| `No such file or directory: /dev/usb/lp0` | Printer not connected or device not passed through | Check `devices:` in docker-compose.yml; verify printer is plugged in |
| `Permission denied on /dev/usb/lp0` | Container user not in `lp` group | Run as root in container, or add udev rule on host |
| Prints garbage / partial output | Wrong printer width setting | Set `dot_width = 576` for 80mm or `384` for 58mm printers |
| `media.width.pixel not set` warning | No printer profile configured | Cosmetic only — does not affect printing |

## Port Conflicts

Check if a port is in use before binding:

```bash
sudo netstat -tlnp | grep 8080
```

(Synology doesn't have `ss` — use `netstat` or `lsof`.)

## Notes

- The printer device path (`/dev/usb/lp0`) can change to `/dev/usb/lp1` if another USB printer is connected. The USB vendor/product IDs (`0fe6:811e`) are permanent.
- No special udev rules are needed on the Synology host — the default `usblp` driver handles everything.
- The container runs as root by default, which has permission to write to the printer device.
