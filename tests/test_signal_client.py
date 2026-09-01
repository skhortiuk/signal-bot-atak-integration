"""Tests for the pure cores of :mod:`signal_atak.signal_client`.

These are the two pieces that must be exactly right: the SSE framing and
the envelope normalisation (especially the Note-to-Self sync-transcript
path). Both are exercised with real signal-cli man-page payloads.
"""

from __future__ import annotations

from signal_atak.messaging.base import InboundMessage
from signal_atak.messaging.signal import normalize_envelope, parse_sse_stream

# --- SSE framing ---------------------------------------------------------- #


def test_sse_basic_event():
    lines = ["event:receive", 'data:{"account":"+1","envelope":{}}', ""]
    events = list(parse_sse_stream(lines))
    assert events == [{"account": "+1", "envelope": {}}]


def test_sse_ignores_comments_and_keepalives():
    lines = [":", ":keep-alive", 'data:{"x":1}', ""]
    assert list(parse_sse_stream(lines)) == [{"x": 1}]


def test_sse_optional_space_after_colon():
    lines = ['data: {"x":2}', ""]
    assert list(parse_sse_stream(lines)) == [{"x": 2}]


def test_sse_multiline_data_joined():
    lines = ["data:{", 'data:"x":3', "data:}", ""]
    assert list(parse_sse_stream(lines)) == [{"x": 3}]


def test_sse_flushes_without_trailing_blank():
    assert list(parse_sse_stream(['data:{"x":4}'])) == [{"x": 4}]


def test_sse_skips_bad_json():
    lines = ["data:not json", "", 'data:{"ok":1}', ""]
    assert list(parse_sse_stream(lines)) == [{"ok": 1}]


# --- envelope normalisation ----------------------------------------------- #


def test_datamessage_from_other_person():
    # verbatim shape from the signal-cli man page
    payload = {
        "envelope": {
            "source": "+33123456789",
            "sourceNumber": "+33123456789",
            "sourceUuid": "uuid",
            "timestamp": 1631458508784,
            "dataMessage": {"timestamp": 1631458508784, "message": "48.5 39.8 tank"},
        }
    }
    msg = normalize_envelope(payload)
    assert msg == InboundMessage(
        source="+33123456789",
        destination="+33123456789",
        text="48.5 39.8 tank",
        timestamp=1631458508784,
        is_sync=False,
    )


def test_note_to_self_sync_transcript():
    """The central case: user's own sent message arrives as a sync transcript."""
    payload = {
        "account": "+33123456789",
        "envelope": {
            "source": "+33123456789",
            "sourceNumber": "+33123456789",
            "timestamp": 1693064367769,
            "syncMessage": {
                "sentMessage": {
                    "destination": "+33123456789",
                    "destinationNumber": "+33123456789",
                    "timestamp": 1693064367769,
                    "message": "48.5 39.8 tank",
                }
            },
        },
    }
    msg = normalize_envelope(payload)
    assert msg is not None
    assert msg.is_sync is True
    assert msg.text == "48.5 39.8 tank"
    assert msg.source == "+33123456789"
    assert msg.destination == "+33123456789"


def test_subscribe_wrapped_envelope_is_unwrapped():
    # subscribeReceive notification nests envelope under params.result
    payload = {
        "jsonrpc": "2.0",
        "method": "receive",
        "params": {
            "subscription": 0,
            "result": {
                "envelope": {
                    "source": "+1",
                    "timestamp": 5,
                    "dataMessage": {"message": "hi"},
                },
                "account": "+1",
            },
        },
    }
    msg = normalize_envelope(payload)
    assert msg is not None
    assert msg.text == "hi"


def test_jsonrpc_notification_params_envelope():
    payload = {
        "jsonrpc": "2.0",
        "method": "receive",
        "params": {"envelope": {"source": "+1", "timestamp": 7, "dataMessage": {"message": "yo"}}},
    }
    assert normalize_envelope(payload).text == "yo"


def test_receipt_only_envelope_returns_none():
    payload = {"envelope": {"source": "+1", "timestamp": 9, "receiptMessage": {"isDelivery": True}}}
    assert normalize_envelope(payload) is None


def test_empty_datamessage_returns_none():
    payload = {"envelope": {"source": "+1", "timestamp": 9, "dataMessage": {"message": None}}}
    assert normalize_envelope(payload) is None


def test_no_envelope_returns_none():
    assert normalize_envelope({"account": "+1"}) is None
