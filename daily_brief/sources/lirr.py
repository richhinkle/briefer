"""Next LIRR departures between two stations, with live delays.

Two data sources, both cached on disk and both degrading gracefully:

  * the **static** LIRR GTFS zip (`stops`, `trips`, `stop_times`,
    `calendar_dates`) gives the day's scheduled trips between the two configured
    stations, and
  * the **realtime** GTFS-realtime `TripUpdates` feed adds a per-train delay.

The realtime feed needs no API key, but parsing it needs the optional
`gtfs-realtime-bindings` library. If that library is missing, the feed is
unreachable, or the protobuf won't parse, the section still prints the plain
schedule — it never fails the print job.

Stations are configured by name (matched against `stops.txt`), so the default
"Port Washington" -> "Penn Station" can be repointed to any pair on the system.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import time
import zipfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from ..brief import KeyVal, Section, Text
from . import _http

log = logging.getLogger(__name__)

GTFS_URL = "https://rrgtfsfeeds.s3.amazonaws.com/gtfslirr.zip"
RT_URL = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/lirr%2Fgtfs-lirr"
AGENCY_TZ = ZoneInfo("America/New_York")  # LIRR runs on NYC local time
USER_AGENT = "daily-brief/0.1 (Raspberry Pi receipt printer)"

STATIC_TTL = 7 * 24 * 3600  # re-download the schedule weekly
RT_TTL = 45                 # realtime feed: short cache so previews don't hammer it


# --- caching helpers -------------------------------------------------------


def _cached_bytes(url: str, ttl: float, prefix: str) -> bytes | None:
    """GET binary content with a TTL file cache + stale fallback (None on fail)."""
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    path = _http.CACHE_DIR / f"{prefix}_{key}.bin"
    if path.is_file() and (time.time() - path.stat().st_mtime) < ttl:
        return path.read_bytes()
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        _http.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(resp.content)
        return resp.content
    except requests.RequestException as exc:
        if path.is_file():
            log.warning("LIRR %s failed (%s); using cached copy", url, exc)
            return path.read_bytes()
        log.warning("LIRR %s failed (%s); no cache available", url, exc)
        return None


# --- static schedule -------------------------------------------------------


def _read_csv(z: zipfile.ZipFile, name: str):
    with z.open(name) as fh:
        yield from csv.DictReader(io.TextIOWrapper(fh, "utf-8"))


def _resolve_stop_ids(z: zipfile.ZipFile, name: str) -> set[str]:
    """All stop_ids whose stop_name matches `name` (case-insensitive)."""
    want = name.strip().lower()
    return {r["stop_id"] for r in _read_csv(z, "stops.txt")
            if r["stop_name"].strip().lower() == want}


def _hms_to_seconds(value: str) -> int:
    """GTFS HH:MM:SS -> seconds past midnight (hours may exceed 24 for late trains)."""
    h, m, s = (int(x) for x in value.split(":"))
    return h * 3600 + m * 60 + s


def _schedule_for(zip_bytes: bytes, origin: str, destination: str, date: str):
    """Trips from `origin` to `destination` active on `date` (YYYYMMDD).

    Returns ``{"origin_ids": [...], "trips": [...]}`` where each trip is
    ``{"dep", "arr", "train", "peak"}`` (dep/arr in seconds past midnight), or
    ``None`` if either station name is unknown.
    """
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    origin_ids = _resolve_stop_ids(z, origin)
    dest_ids = _resolve_stop_ids(z, destination)
    if not origin_ids or not dest_ids:
        return None

    # LIRR has no calendar.txt; service is defined entirely by calendar_dates.
    services = {r["service_id"] for r in _read_csv(z, "calendar_dates.txt")
                if r["date"] == date and r["exception_type"] == "1"}
    trips = {r["trip_id"]: r for r in _read_csv(z, "trips.txt")
             if r["service_id"] in services}

    # One streaming pass over stop_times, keeping our two stops per trip.
    legs: dict[str, dict] = {}
    for r in _read_csv(z, "stop_times.txt"):
        tid = r["trip_id"]
        if tid not in trips:
            continue
        seq = int(r["stop_sequence"])
        if r["stop_id"] in origin_ids:
            leg = legs.setdefault(tid, {})
            if seq < leg.get("o_seq", 1 << 30):
                leg["o_seq"], leg["dep"] = seq, _hms_to_seconds(r["departure_time"])
        elif r["stop_id"] in dest_ids:
            leg = legs.setdefault(tid, {})
            if seq < leg.get("d_seq", 1 << 30):
                leg["d_seq"], leg["arr"] = seq, _hms_to_seconds(r["arrival_time"])

    out = []
    for tid, leg in legs.items():
        if "o_seq" in leg and "d_seq" in leg and leg["o_seq"] < leg["d_seq"]:
            t = trips[tid]
            out.append({
                "dep": leg["dep"], "arr": leg["arr"],
                "train": (t.get("trip_short_name") or "").strip(),
                "peak": str(t.get("peak_offpeak", "")).strip() == "1",
            })
    out.sort(key=lambda x: x["dep"])
    return {"origin_ids": sorted(origin_ids), "trips": out}


def _cached_schedule(origin: str, destination: str, date: str):
    """Day's schedule for a station pair, cached so the GTFS parse runs once/day."""
    key = f"lirr:sched:{origin.lower()}:{destination.lower()}:{date}"
    cached = _http.cache_get(key, ttl=12 * 3600)
    if cached is not None:
        return cached
    data = _cached_bytes(GTFS_URL, STATIC_TTL, "lirr_gtfs")
    if not data:
        return None
    sched = _schedule_for(data, origin, destination, date)
    if sched is not None:  # don't cache an unknown-station miss
        _http.cache_set(key, sched)
    return sched


# --- realtime delays -------------------------------------------------------


def _realtime_delays(origin_ids: set[str]) -> dict[str, int]:
    """Map train number -> departure delay (seconds) at the origin, best-effort."""
    try:
        from google.transit import gtfs_realtime_pb2
    except Exception:
        return {}  # bindings not installed -> schedule-only
    data = _cached_bytes(RT_URL, RT_TTL, "lirr_rt")
    if not data:
        return {}
    try:
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(data)
    except Exception as exc:  # pragma: no cover - corrupt feed
        log.warning("LIRR realtime parse failed: %s", exc)
        return {}

    delays: dict[str, int] = {}
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        tu = entity.trip_update
        # Realtime trip_ids are variants of the static ones (e.g. GO201_26_6008_1);
        # the train number is the third underscore-separated field.
        parts = tu.trip.trip_id.split("_")
        train = parts[2] if len(parts) > 2 else ""
        if not train:
            continue
        for stu in tu.stop_time_update:
            if stu.stop_id not in origin_ids:
                continue
            if stu.HasField("departure") and stu.departure.HasField("delay"):
                delays[train] = stu.departure.delay
            elif stu.HasField("arrival") and stu.arrival.HasField("delay"):
                delays[train] = stu.arrival.delay
            break
    return delays


# --- section ---------------------------------------------------------------


def _status(delay: int | None, peak: bool) -> str:
    """Right-hand status text: delay if known, else a peak marker."""
    if delay is None:
        return "peak" if peak else ""
    minutes = round(delay / 60)
    if minutes <= 0:
        return "on time"
    return f"+{minutes} min"


def build(section_cfg, ctx) -> Section:
    title = section_cfg.title or "LIRR"
    origin = str(section_cfg.get("origin", "Port Washington"))
    destination = str(section_cfg.get("destination", "Penn Station"))
    count = max(1, min(12, int(section_cfg.get("count", 4))))
    use_realtime = bool(section_cfg.get("realtime", True))

    now = ctx.now.astimezone(AGENCY_TZ) if ctx.now.tzinfo else datetime.now(AGENCY_TZ)
    date = now.strftime("%Y%m%d")
    now_sec = now.hour * 3600 + now.minute * 60 + now.second

    sched = _cached_schedule(origin, destination, date)
    if sched is None:
        return Section(title, [Text(f"(no station {origin!r} or {destination!r})")])

    # Today's service only; trains just departed (last 60s) are still useful.
    upcoming = [t for t in sched["trips"] if t["dep"] >= now_sec - 60][:count]
    if not upcoming:
        return Section(title, [Text("No more trains today.")])

    delays = _realtime_delays(set(sched["origin_ids"])) if use_realtime else {}

    midnight = datetime(now.year, now.month, now.day, tzinfo=AGENCY_TZ)
    fmt = ctx.config.render.format_time
    items = []
    for t in upcoming:
        dep = fmt(midnight + timedelta(seconds=t["dep"]))
        arr = fmt(midnight + timedelta(seconds=t["arr"]))
        items.append(KeyVal(f"{dep} → {arr}", _status(delays.get(t["train"]), t["peak"])))
    return Section(title, items)
