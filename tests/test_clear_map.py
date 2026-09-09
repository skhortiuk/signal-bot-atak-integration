"""Tests for the clear/retract flow: clear_map uid reader + listener MapWriter."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from signal_atak.output.cot.encode import CotEvent

_TOOLS = Path(__file__).resolve().parent.parent / "tools"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


clear_map = _load("clear_map")
cot_listener = _load("cot_listener")


def _event(uid: str, cot_type: str = "a-h-G-E-V-A-T") -> CotEvent:
    return CotEvent(uid=uid, type=cot_type, lat=48.5, lon=39.8, callsign=uid)


# --- clear_map._read_uids ------------------------------------------------- #


def test_read_uids_dedupes_preserving_order(tmp_path):
    state = tmp_path / "emitted.txt"
    state.write_text("signal-a\nsignal-b\nsignal-a\n\n  signal-c  \n")
    assert clear_map._read_uids(state) == ["signal-a", "signal-b", "signal-c"]


def test_read_uids_missing_file_is_empty(tmp_path):
    assert clear_map._read_uids(tmp_path / "nope.txt") == []


# --- listener MapWriter add / remove / clear ------------------------------ #


def test_mapwriter_add_remove_clear(tmp_path):
    mw = cot_listener.MapWriter(tmp_path / "map.html")
    mw.add(_event("signal-1"))
    mw.add(_event("signal-2"))
    assert len(mw._events) == 2

    mw.remove("signal-1")
    assert [e.uid for e in mw._events] == ["signal-2"]

    mw.remove("does-not-exist")  # no-op, must not raise
    assert len(mw._events) == 1

    mw.clear()
    assert mw._events == []
    assert (tmp_path / "map.html").is_file()  # empty map still written


def test_mapwriter_add_same_uid_replaces(tmp_path):
    mw = cot_listener.MapWriter(tmp_path / "map.html")
    mw.add(_event("signal-1", "a-h-G-E-V-A-T"))
    mw.add(_event("signal-1", "a-h-G-U-C-I"))  # same uid, updated type
    assert len(mw._events) == 1
    assert mw._events[0].type == "a-h-G-U-C-I"
