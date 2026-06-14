"""Scheduler: due-detection, day filtering, no double-fire, tick wiring."""

from __future__ import annotations

import datetime

from daily_brief import daemon
from daily_brief.config import Config, ScheduleConfig


def _cfg():
    return Config(schedules=[
        ScheduleConfig(name="morning", brief="m", time="07:30"),                 # daily
        ScheduleConfig(name="weekday", brief="w", time="12:00",
                       days=["mon", "tue", "wed", "thu", "fri"]),
        ScheduleConfig(name="off", brief="x", time="07:30", enabled=False),
    ])


def test_daily_fires_any_day():
    sat = datetime.datetime(2026, 6, 13, 7, 30)  # Saturday
    fired = daemon.due_schedules(_cfg(), sat, {})
    assert [s.name for s in fired] == ["morning"]  # weekday excluded, off disabled


def test_weekday_only():
    mon_noon = datetime.datetime(2026, 6, 15, 12, 0)  # Monday
    assert [s.name for s in daemon.due_schedules(_cfg(), mon_noon, {})] == ["weekday"]
    sun_noon = datetime.datetime(2026, 6, 14, 12, 0)  # Sunday
    assert daemon.due_schedules(_cfg(), sun_noon, {}) == []


def test_no_double_fire_same_day():
    cfg, last = _cfg(), {}
    t = datetime.datetime(2026, 6, 15, 7, 30)
    assert len(daemon.due_schedules(cfg, t, last)) == 1
    assert daemon.due_schedules(cfg, t, last) == []           # already fired
    assert len(daemon.due_schedules(cfg, t.replace(day=16), last)) == 1  # next day fires


def test_tick_prints_due_brief(monkeypatch, tmp_path):
    printed = []
    monkeypatch.setattr(daemon, "print_brief", lambda cfg, name: printed.append(name))
    sch = daemon.Scheduler(config_path=tmp_path / "none.toml")  # missing file -> empty
    sch.config = _cfg()
    sch.tick(datetime.datetime(2026, 6, 15, 7, 30))  # Monday 07:30
    assert printed == ["m"]
