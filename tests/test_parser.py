"""Tests for :mod:`signal_atak.parser`."""

from __future__ import annotations

import pytest

from signal_atak.parser import InvalidCoordinateError, Target, parse_target


def test_parses_basic_lat_lon_description():
    t = parse_target("48.567123 39.87897 tank")
    assert t == Target(lat=48.567123, lon=39.87897, description="tank")


def test_multiword_description_preserved():
    t = parse_target("48.5 39.8 enemy APC near the bridge")
    assert t is not None
    assert t.description == "enemy APC near the bridge"


def test_comma_separator():
    t = parse_target("48.567123, 39.87897, tank")
    assert t is not None
    assert (t.lat, t.lon, t.description) == (48.567123, 39.87897, "tank")


def test_comma_without_spaces():
    t = parse_target("48.5,39.8,truck")
    assert t is not None
    assert (t.lat, t.lon) == (48.5, 39.8)


def test_negative_coordinates():
    t = parse_target("-33.9 18.4 vehicle")
    assert t is not None
    assert (t.lat, t.lon) == (-33.9, 18.4)


def test_integer_coordinates():
    t = parse_target("48 39 tank")
    assert t is not None
    assert (t.lat, t.lon) == (48.0, 39.0)


def test_lon_first_swaps_order():
    t = parse_target("39.87897 48.567123 tank", lon_first=True)
    assert t is not None
    assert (t.lat, t.lon) == (48.567123, 39.87897)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "hello there",
        "just one 48.5 number word",  # 'just' is not numeric -> no leading coord pair
        "✅ sent tank to ATAK",  # a bot reply must not re-trigger
        "48.5 tank",  # only one number
        "meeting at 5pm",
    ],
)
def test_non_target_text_returns_none(text):
    assert parse_target(text) is None


def test_out_of_range_latitude_raises():
    with pytest.raises(InvalidCoordinateError, match="Latitude"):
        parse_target("100.0 20.0 tank")


def test_out_of_range_longitude_raises():
    with pytest.raises(InvalidCoordinateError, match="Longitude"):
        parse_target("45.0 200.0 tank")


def test_swapped_order_warns_but_still_parses(caplog):
    # 120 cannot be a latitude, 45 could be -> warn, but don't silently reorder
    import logging

    with caplog.at_level(logging.WARNING), pytest.raises(InvalidCoordinateError):
        parse_target("120.0 45.0 tank")
    assert any("looks swapped" in r.message for r in caplog.records)


def test_target_validators_reject_direct_construction():
    with pytest.raises(ValueError):
        Target(lat=999.0, lon=0.0, description="x")
    with pytest.raises(ValueError):
        Target(lat=0.0, lon=0.0, description="")
