"""LIRR section: schedule parsing and status formatting (offline)."""

from __future__ import annotations

import io
import zipfile

from daily_brief.sources import lirr


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, body in files.items():
            z.writestr(name, body)
    return buf.getvalue()


# A tiny GTFS: stations A (origin) and B (destination), one service date.
_GTFS = _make_zip({
    "stops.txt": (
        "stop_id,stop_name\n"
        "1,Alpha\n"
        "2,Beta\n"
        "3,Gamma\n"
    ),
    "calendar_dates.txt": (
        "service_id,date,exception_type\n"
        "WK,20260101,1\n"     # active on our test date
        "WK,20260102,1\n"
        "WE,20260101,2\n"     # removed exception, must be ignored
    ),
    "trips.txt": (
        "route_id,service_id,trip_id,trip_short_name,peak_offpeak\n"
        "P,WK,t_fwd,100,1\n"      # Alpha -> Beta, peak
        "P,WK,t_rev,200,0\n"      # Beta -> Alpha (wrong direction)
        "P,WK,t_late,300,0\n"     # Alpha -> Beta after midnight (25:10)
        "P,OTHER,t_off,400,0\n"   # service not active on the date
    ),
    "stop_times.txt": (
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "t_fwd,08:00:00,08:00:00,1,1\n"
        "t_fwd,08:30:00,08:30:00,2,2\n"
        "t_rev,09:00:00,09:00:00,2,1\n"
        "t_rev,09:30:00,09:30:00,1,2\n"
        "t_late,25:10:00,25:10:00,1,1\n"
        "t_late,25:40:00,25:40:00,2,2\n"
        "t_off,07:00:00,07:00:00,1,1\n"
        "t_off,07:30:00,07:30:00,2,2\n"
    ),
})


def test_schedule_only_matches_origin_to_destination():
    sched = lirr._schedule_for(_GTFS, "Alpha", "Beta", "20260101")
    assert sched is not None
    trains = [t["train"] for t in sched["trips"]]
    # Forward trip and the after-midnight trip, in departure order; the reverse
    # trip and the out-of-service trip are excluded.
    assert trains == ["100", "300"]
    assert sched["origin_ids"] == ["1"]
    fwd = sched["trips"][0]
    assert fwd["dep"] == 8 * 3600 and fwd["peak"] is True
    # 25:10 stays as seconds past midnight (> 24h) rather than wrapping.
    assert sched["trips"][1]["dep"] == 25 * 3600 + 10 * 60


def test_schedule_unknown_station_returns_none():
    assert lirr._schedule_for(_GTFS, "Alpha", "Nowhere", "20260101") is None


def test_status_formatting():
    assert lirr._status(None, peak=True) == "peak"
    assert lirr._status(None, peak=False) == ""
    assert lirr._status(0, peak=False) == "on time"
    assert lirr._status(-30, peak=False) == "on time"   # early counts as on time
    assert lirr._status(360, peak=False) == "+6 min"
