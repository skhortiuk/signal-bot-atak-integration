"""Tests for the CoT delete/retract path (build_delete_cot + parse + listener)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from signal_atak.output.cot.encode import DELETE_TYPE, build_delete_cot, parse_cot


def test_build_delete_cot_is_wellformed_and_typed():
    raw = build_delete_cot("signal-abc-123")
    event = ET.fromstring(raw)
    assert event.tag == "event"
    assert event.attrib["type"] == DELETE_TYPE
    link = event.find("./detail/link")
    assert link is not None
    assert link.attrib["uid"] == "signal-abc-123"
    # a forcedelete hint and a (schema-required) point are present
    assert event.find("./detail/__forcedelete") is not None
    assert event.find("point") is not None


def test_parse_cot_flags_delete_and_extracts_link():
    event = parse_cot(build_delete_cot("signal-target-9"))
    assert event.is_delete is True
    assert event.link_uid == "signal-target-9"


def test_parse_cot_regular_event_is_not_delete():
    from signal_atak.output.cot.encode import build_cot
    from signal_atak.parser import Target

    event = parse_cot(build_cot(Target(lat=1.0, lon=2.0, description="tank")))
    assert event.is_delete is False
    assert event.link_uid == ""
