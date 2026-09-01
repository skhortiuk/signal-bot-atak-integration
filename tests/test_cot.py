"""Tests for :mod:`signal_atak.cot`."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from signal_atak.output.cot.encode import UNKNOWN, build_cot
from signal_atak.parser import Target

_FIXED_NOW = datetime(2026, 8, 31, 12, 0, 0, 500_000, tzinfo=UTC)
_FIXED_UID = "signal-11112222-3333-4444-5555-666677778888"


def _build(**kw):
    target = kw.pop("target", Target(lat=48.567123, lon=39.87897, description="tank"))
    return build_cot(target, now=_FIXED_NOW, uid=_FIXED_UID, **kw)


def test_output_is_wellformed_xml_with_declaration():
    raw = _build()
    assert raw.startswith(b"<?xml")
    ET.fromstring(raw)  # raises on malformed XML


def test_event_attributes():
    event = ET.fromstring(_build())
    assert event.tag == "event"
    assert event.attrib["version"] == "2.0"
    assert event.attrib["uid"] == _FIXED_UID
    assert event.attrib["type"] == "a-h-G-E-V-A-T"
    assert event.attrib["how"] == "m-g"


def test_time_format_iso8601_millis_z():
    event = ET.fromstring(_build())
    assert event.attrib["time"] == "2026-08-31T12:00:00.500Z"
    assert event.attrib["start"] == "2026-08-31T12:00:00.500Z"
    # default stale is +10 minutes
    assert event.attrib["stale"] == "2026-08-31T12:10:00.500Z"


def test_stale_minutes_override():
    event = ET.fromstring(_build(stale_minutes=2))
    assert event.attrib["stale"] == "2026-08-31T12:02:00.500Z"


def test_point_carries_coords_and_unknown_accuracy():
    point = ET.fromstring(_build()).find("point")
    assert point is not None
    assert point.attrib["lat"] == "48.567123"
    assert point.attrib["lon"] == "39.87897"
    assert point.attrib["hae"] == UNKNOWN
    assert point.attrib["ce"] == UNKNOWN
    assert point.attrib["le"] == UNKNOWN


def test_detail_contact_and_remarks():
    detail = ET.fromstring(_build()).find("detail")
    assert detail is not None
    contact = detail.find("contact")
    assert contact is not None
    assert contact.attrib["callsign"].startswith("tank-")
    remarks = detail.find("remarks")
    assert remarks is not None
    assert remarks.text == "48.567123 39.87897 tank"


def test_type_reflects_affiliation():
    event = ET.fromstring(_build(affiliation="f"))
    assert event.attrib["type"] == "a-f-G-E-V-A-T"


def test_default_uid_is_unique_and_prefixed():
    target = Target(lat=1.0, lon=2.0, description="truck")
    uid1 = ET.fromstring(build_cot(target)).attrib["uid"]
    uid2 = ET.fromstring(build_cot(target)).attrib["uid"]
    assert uid1.startswith("signal-")
    assert uid1 != uid2


def test_coords_near_zero_are_not_scientific_notation():
    # f"{1e-05}" == "1e-05", which violates xs:decimal and can misparse in TAK.
    point = ET.fromstring(_build(target=Target(lat=0.00001, lon=-0.000002, description="x"))).find(
        "point"
    )
    assert point.attrib["lat"] == "0.00001"
    assert point.attrib["lon"] == "-0.000002"
    assert "e" not in point.attrib["lat"].lower()
    assert "e" not in point.attrib["lon"].lower()


def test_integer_coord_has_no_trailing_dot():
    point = ET.fromstring(_build(target=Target(lat=48.0, lon=39.0, description="x"))).find("point")
    assert point.attrib["lat"] == "48"
    assert point.attrib["lon"] == "39"


def test_time_converted_to_utc_before_z_suffix():
    from datetime import timedelta, timezone

    kyiv = timezone(timedelta(hours=3))
    # 12:00 +03:00 is 09:00Z — the Z timestamp must show 09:00, not 12:00.
    event = ET.fromstring(
        build_cot(
            Target(lat=1.0, lon=2.0, description="tank"),
            now=datetime(2026, 8, 31, 12, 0, 0, tzinfo=kyiv),
            uid=_FIXED_UID,
        )
    )
    assert event.attrib["time"] == "2026-08-31T09:00:00.000Z"
