"""Tests for :func:`signal_atak.cot.parse_cot` — the listener's decode path."""

from __future__ import annotations

import pytest

from signal_atak.output.cot.encode import CotParseError, build_cot, parse_cot
from signal_atak.parser import Target


def test_roundtrip_build_then_parse():
    target = Target(lat=48.567123, lon=39.87897, description="tank")
    event = parse_cot(build_cot(target))
    assert event.type == "a-h-G-E-V-A-T"
    assert (event.lat, event.lon) == (48.567123, 39.87897)
    assert event.callsign.startswith("tank-")
    assert event.remarks == "48.567123 39.87897 tank"
    assert event.uid.startswith("signal-")


def test_rejects_non_event_root():
    with pytest.raises(CotParseError, match="expected <event>"):
        parse_cot(b"<notanevent/>")


def test_rejects_missing_point():
    with pytest.raises(CotParseError, match="no <point>"):
        parse_cot(b"<event version='2.0'></event>")


def test_rejects_malformed_xml():
    with pytest.raises(CotParseError, match="well-formed"):
        parse_cot(b"<event <<<")


def test_rejects_bad_point_coords():
    with pytest.raises(CotParseError, match="lat/lon"):
        parse_cot(b"<event><point lat='x' lon='y'/></event>")


def test_xxe_entity_is_not_expanded():
    """defusedxml must refuse an external-entity payload rather than resolve it."""
    payload = (
        b"<?xml version='1.0'?>"
        b"<!DOCTYPE event [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]>"
        b"<event><point lat='1' lon='2'/><detail><remarks>&xxe;</remarks></detail></event>"
    )
    with pytest.raises(CotParseError):
        parse_cot(payload)
