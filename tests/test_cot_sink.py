"""Tests for :class:`signal_atak.output.cot_sink.CotSink`.

The sink is the seam between CoT encoding and the byte transport; here we
drive it with a recording fake transport and assert it emits valid CoT
carrying the configured affiliation/stale, and that transport failures
propagate as OSError for the bot to catch.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from signal_atak.output.cot_sink import CotSink
from signal_atak.parser import Target


class RecordingTransport:
    def __init__(self):
        self.payloads: list[bytes] = []
        self.closed = False

    def send(self, payload):
        self.payloads.append(payload)

    def close(self):
        self.closed = True


class FailingTransport:
    def send(self, payload):
        raise OSError("no route to host")

    def close(self):
        pass


def test_emit_produces_valid_cot_with_type():
    transport = RecordingTransport()
    CotSink(transport).emit(Target(lat=48.567123, lon=39.87897, description="tank"))

    assert len(transport.payloads) == 1
    event = ET.fromstring(transport.payloads[0])
    assert event.tag == "event"
    assert event.attrib["type"] == "a-h-G-E-V-A-T"
    assert event.find("point").attrib["lat"] == "48.567123"


def test_affiliation_and_stale_are_threaded_through():
    transport = RecordingTransport()
    CotSink(transport, affiliation="f", stale_minutes=2).emit(
        Target(lat=1.0, lon=2.0, description="tank")
    )
    event = ET.fromstring(transport.payloads[0])
    assert event.attrib["type"] == "a-f-G-E-V-A-T"
    # 2-minute lifetime: stale must differ from start
    assert event.attrib["stale"] != event.attrib["start"]


def test_transport_failure_propagates_as_oserror():
    with pytest.raises(OSError):
        CotSink(FailingTransport()).emit(Target(lat=1.0, lon=2.0, description="tank"))


def test_close_closes_transport():
    transport = RecordingTransport()
    CotSink(transport).close()
    assert transport.closed is True


def test_emit_records_uid_to_state_file(tmp_path):
    state = tmp_path / "emitted.txt"
    sink = CotSink(RecordingTransport(), state_path=state)
    sink.emit(Target(lat=1.0, lon=2.0, description="tank"))
    sink.emit(Target(lat=3.0, lon=4.0, description="truck"))

    uids = state.read_text().split()
    assert len(uids) == 2
    assert all(u.startswith("signal-") for u in uids)
    assert uids[0] != uids[1]


def test_recorded_uid_matches_emitted_marker_uid(tmp_path):
    """The uid written to state must be the uid inside the emitted CoT."""
    state = tmp_path / "emitted.txt"
    transport = RecordingTransport()
    CotSink(transport, state_path=state).emit(Target(lat=1.0, lon=2.0, description="tank"))

    emitted_uid = ET.fromstring(transport.payloads[0]).attrib["uid"]
    assert state.read_text().strip() == emitted_uid


def test_no_state_path_means_no_file(tmp_path):
    # default: state_path is None → nothing written, no crash
    CotSink(RecordingTransport()).emit(Target(lat=1.0, lon=2.0, description="tank"))
    assert list(tmp_path.iterdir()) == []
