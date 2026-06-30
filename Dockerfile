# Dockerfile for running Daily Brief on a NAS (Synology, etc.)
# Strips Pi-specific dependencies (GPIO, AP/WiFi) and runs the daemon
# with the web console + scheduler in a single container.

FROM python:3.11-slim

# System deps for python-escpos USB backend and Pillow image rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    libusb-1.0-0 \
    libjpeg62-turbo \
    libfreetype6 \
    libopenjp2-7 \
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

# Run the daemon with --no-setup to skip AP/WiFi/button state machine.
# The scheduler + web console still run.
ENTRYPOINT ["python", "-m", "daily_brief.daemon", "--no-setup"]
CMD ["--config", "/app/config.toml"]
