# Dockerfile for running Daily Brief on a NAS (Synology, etc.)
# Strips Pi-specific dependencies (GPIO, AP/WiFi) and runs the daemon
# with the web console + scheduler in a single container.

FROM python:3.11

# python:3.11 (full image) already includes imaging libraries (libjpeg, freetype,
# openjp2, etc.) so we only need libusb for the thermal printer backend.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libusb-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (skip gpiozero/lgpio - no GPIO on NAS)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY daily_brief/ daily_brief/
COPY scripts/ scripts/

# Config is mounted as a volume; provide the example as a fallback
COPY config.example.toml /app/config.example.toml

# The web console runs on port 80 by default
EXPOSE 80

# Run the full daemon (Controller mode). On a NAS without GPIO/nmcli it
# gracefully skips AP/button handling but still starts the web console +
# scheduler. The web console provides the config UI at http://<nas-ip>:8080.
ENTRYPOINT ["python", "-m", "daily_brief.daemon"]
CMD ["--config", "/app/data/config.toml"]
