"""Unit tests for the API access layer (lumen.sources).

These cover the pure parsing/mapping logic against representative payloads;
no network involved. The HTTP wrappers are thin enough that their behaviour
is exercised implicitly through these parsers.
"""

from __future__ import annotations

from datetime import date, datetime

from lumen.scenes.transit import _stop_entries
from lumen.sources.github import contribution_stats, parse_calendar
from lumen.sources.rmv import StopSpec, parse_departures
from lumen.sources.weather import condition_from_code, parse_report

# -- GitHub ------------------------------------------------------------------

TODAY = date(2026, 6, 6)


def _calendar(counts: dict[str, int]) -> dict:
    return {
        "weeks": [
            {"contributionDays": [{"date": d, "contributionCount": n}]}
            for d, n in counts.items()
        ]
    }


def test_github_stats_basic():
    days = parse_calendar(
        _calendar(
            {
                "2026-05-31": 2,
                "2026-06-01": 5,
                "2026-06-02": 1,
                "2026-06-03": 8,
                "2026-06-04": 3,
                "2026-06-05": 6,
                "2026-06-06": 7,
            }
        )
    )
    stats = contribution_stats(days, TODAY)
    assert stats.today == 7
    assert stats.week == [2, 5, 1, 8, 3, 6, 7]
    assert stats.streak == 7


def test_github_streak_broken_by_gap():
    days = parse_calendar(
        _calendar({"2026-06-03": 4, "2026-06-04": 0, "2026-06-05": 2, "2026-06-06": 1})
    )
    assert contribution_stats(days, TODAY).streak == 2


def test_github_zero_today_keeps_streak_from_yesterday():
    # The day isn't over: 0 contributions today must not zero the streak.
    days = parse_calendar(
        _calendar({"2026-06-04": 1, "2026-06-05": 3, "2026-06-06": 0})
    )
    stats = contribution_stats(days, TODAY)
    assert stats.today == 0
    assert stats.streak == 2


def test_github_missing_days_count_as_zero():
    stats = contribution_stats(parse_calendar(_calendar({"2026-06-06": 9})), TODAY)
    assert stats.week == [0, 0, 0, 0, 0, 0, 9]
    assert stats.streak == 1


# -- RMV ---------------------------------------------------------------------

NOW = datetime(2026, 6, 6, 9, 30, 0)


def _departure(**over) -> dict:
    dep = {
        "name": "Bus 73",
        "direction": "Enkheim",
        "date": "2026-06-06",
        "time": "09:35:00",
        "Product": {"line": "73", "catOut": "Bus"},
    }
    dep.update(over)
    return dep


def test_rmv_basic_parse():
    rows = parse_departures({"Departure": [_departure()]}, now=NOW)
    assert len(rows) == 1
    d = rows[0]
    assert d.line == "73"
    assert d.direction == "Enkheim"
    assert d.when == datetime(2026, 6, 6, 9, 35, 0)
    assert d.color == (160, 90, 220)  # Bus category fallback


def test_rmv_realtime_wins_and_sorts():
    rows = parse_departures(
        {
            "Departure": [
                _departure(time="09:32:00", rtTime="09:40:00", rtDate="2026-06-06"),
                _departure(time="09:36:00"),
            ]
        },
        now=NOW,
    )
    assert [r.when.minute for r in rows] == [36, 40]


def test_rmv_skips_cancelled_and_departed():
    rows = parse_departures(
        {
            "Departure": [
                _departure(cancelled=True),
                _departure(time="09:10:00"),  # already gone
                _departure(time="09:45:00"),
            ]
        },
        now=NOW,
    )
    assert len(rows) == 1
    assert rows[0].when.minute == 45


def test_rmv_single_departure_object():
    # A single XML element converts to an object, not a one-element array.
    rows = parse_departures({"Departure": _departure()}, now=NOW)
    assert len(rows) == 1


def test_rmv_icon_color_used_unless_too_dark():
    bright = _departure(
        Product={"line": "S6", "icon": {"backgroundColor": {"r": 0, "g": 153, "b": 80}}}
    )
    dark = _departure(
        Product={
            "line": "N1",
            "catOut": "Bus",
            "icon": {"backgroundColor": {"r": 0, "g": 0, "b": 0}},
        }
    )
    rows = parse_departures({"Departure": [bright, dark]}, now=NOW)
    assert rows[0].color == (0, 153, 80)
    assert rows[1].color == (160, 90, 220)  # near-black falls back to category


def test_rmv_line_label_fallback_to_name():
    dep = _departure(Product={}, name="S 9")
    rows = parse_departures({"Departure": [dep]}, now=NOW)
    assert rows[0].line == "9"


def test_rmv_product_array_takes_first():
    dep = _departure(Product=[{"line": "U4", "catOut": "U"}, {"line": "X", "catOut": "Bus"}])
    rows = parse_departures({"Departure": [dep]}, now=NOW)
    assert rows[0].line == "U4"
    assert rows[0].color == (220, 60, 60)


def test_rmv_delay_from_realtime():
    rows = parse_departures(
        {
            "Departure": [
                _departure(time="09:32:00", rtTime="09:40:00", rtDate="2026-06-06"),
                _departure(time="09:36:00", rtTime="09:36:00", rtDate="2026-06-06"),
                _departure(time="09:50:00"),  # no realtime data
                _departure(time="10:05:00", rtTime="10:03:00", rtDate="2026-06-06"),
            ]
        },
        now=NOW,
    )
    assert [r.delay_min for r in rows] == [0, 8, None, -2]  # sorted by effective time


def test_rmv_line_filter_case_insensitive():
    deps = [
        _departure(Product={"line": "U16", "catOut": "U"}),
        _departure(Product={"line": "73", "catOut": "Bus"}, time="09:40:00"),
    ]
    rows = parse_departures({"Departure": deps}, now=NOW, lines=["u16"])
    assert [r.line for r in rows] == ["U16"]
    # Integer codes work too (TOML: lines = [73]).
    rows = parse_departures({"Departure": deps}, now=NOW, lines=[73])
    assert [r.line for r in rows] == ["73"]


# -- transit scene config ------------------------------------------------------


def test_stop_entries_single_stop_id():
    assert _stop_entries({"stop_id": "3000010"}) == [StopSpec("3000010")]
    assert _stop_entries({"stop_id": "3000010", "lines": ["U16"]}) == [
        StopSpec("3000010", lines=["U16"])
    ]


def test_stop_entries_multiple_stations():
    cfg = {
        "stops": ["3000010", {"id": "3000011", "lines": ["U4", "U16"]}],
        "lines": ["S6"],
    }
    assert _stop_entries(cfg) == [
        StopSpec("3000010", lines=["S6"]),  # global filter applies where no per-station one
        StopSpec("3000011", lines=["U4", "U16"]),
    ]


def test_stop_entries_stops_take_precedence_over_stop_id():
    cfg = {"stops": ["1"], "stop_id": "2"}
    assert _stop_entries(cfg) == [StopSpec("1")]
    assert _stop_entries({}) == []


def test_stop_entries_direction():
    cfg = {
        "stops": ["3000010", {"id": "3000011", "direction": 3001234}],
        "direction": "3009999",
    }
    assert _stop_entries(cfg) == [
        StopSpec("3000010", direction="3009999"),  # global fallback
        StopSpec("3000011", direction="3001234"),  # per-station wins, coerced to str
    ]
    assert _stop_entries({"stop_id": "1", "direction": "3009999"}) == [
        StopSpec("1", direction="3009999")
    ]


def test_transit_compact_mode_renders():
    from lumen import FRAME_BYTES
    from lumen.config import Config
    from lumen.scene import RenderContext
    from lumen.scenes.transit import TransitScene

    scene = TransitScene()
    full = RenderContext(now=NOW, config=Config())
    compact = RenderContext(now=NOW, config=Config(scenes={"transit": {"mode": "compact"}}))

    full_frame = scene.render(full).to_rgb565()
    compact_frame = scene.render(compact).to_rgb565()
    assert len(full_frame) == FRAME_BYTES
    assert len(compact_frame) == FRAME_BYTES
    assert full_frame != compact_frame  # the mode switch must change the layout


# -- weather -------------------------------------------------------------------


def test_weather_condition_mapping():
    assert condition_from_code(0) == "clear"
    assert condition_from_code(1) == "clear"
    assert condition_from_code(3) == "clouds"
    assert condition_from_code(45) == "clouds"  # fog
    assert condition_from_code(61) == "rain"
    assert condition_from_code(81) == "rain"  # showers
    assert condition_from_code(95) == "rain"  # thunderstorm
    assert condition_from_code(71) == "snow"
    assert condition_from_code(86) == "snow"  # snow showers
    assert condition_from_code(1234) == "clouds"  # unknown -> safe default


def test_weather_parse_report():
    payload = {
        "current": {"temperature_2m": 18.3, "weather_code": 2},
        "daily": {"temperature_2m_max": [21.0], "temperature_2m_min": [11.2]},
    }
    report = parse_report(payload)
    assert report.temp_c == 18.3
    assert report.high_c == 21.0
    assert report.low_c == 11.2
    assert report.condition == "clouds"
