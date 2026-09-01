"""Tests for :class:`signal_atak.bot.Bot` with fake collaborators.

No network: a fake messenger records replies, a fake sink records emitted
targets. This asserts the end-to-end behaviour and, crucially, that the
bot does NOT loop on its own replies. CoT-encoding correctness lives in
test_cot_sink.py — the bot itself is output-agnostic.
"""

from __future__ import annotations

import pytest

from signal_atak.bot import Bot
from signal_atak.config import Config
from signal_atak.messaging.base import InboundMessage
from signal_atak.parser import Target

ACCOUNT = "+33123456789"


class FakeMessenger:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send(self, recipient, text):
        self.sent.append((recipient, text))

    def receive(self):  # pragma: no cover - not used in handle() tests
        yield from ()


class FakeSink:
    def __init__(self):
        self.emitted: list[Target] = []
        self.fail = False

    def emit(self, target):
        if self.fail:
            raise OSError("network down")
        self.emitted.append(target)

    def close(self):
        pass


def _bot(config=None):
    cfg = config or Config(signal_account=ACCOUNT, cot_url="log://stdout")
    messenger, sink = FakeMessenger(), FakeSink()
    return Bot(cfg, messenger, sink), messenger, sink


def _msg(text, *, ts=1, source=ACCOUNT, destination=ACCOUNT, is_sync=True):
    return InboundMessage(
        source=source, destination=destination, text=text, timestamp=ts, is_sync=is_sync
    )


def test_note_to_self_target_is_emitted_and_replied():
    bot, messenger, sink = _bot()
    bot.handle(_msg("48.567123 39.87897 tank"))

    assert len(sink.emitted) == 1
    assert sink.emitted[0] == Target(lat=48.567123, lon=39.87897, description="tank")
    assert len(messenger.sent) == 1
    recipient, reply = messenger.sent[0]
    assert recipient == ACCOUNT
    assert reply.startswith("✅")
    assert "tank" in reply


def test_does_not_loop_on_its_own_reply():
    """The bot's ✅ reply, fed back as a sync transcript, must be ignored."""
    bot, messenger, sink = _bot()
    bot.handle(_msg("48.5 39.8 tank", ts=1))
    reply_text = messenger.sent[0][1]

    bot.handle(_msg(reply_text, ts=2))  # the reply echoing back
    assert len(sink.emitted) == 1  # no second emit
    assert len(messenger.sent) == 1  # no reply to the reply


def test_duplicate_timestamp_ignored():
    bot, messenger, sink = _bot()
    bot.handle(_msg("48.5 39.8 tank", ts=42))
    bot.handle(_msg("48.5 39.8 tank", ts=42))  # same ts = duplicate delivery
    assert len(sink.emitted) == 1


def test_ordinary_chatter_is_silent():
    bot, messenger, sink = _bot()
    bot.handle(_msg("hey are we still on for lunch?", ts=3))
    assert sink.emitted == []
    assert messenger.sent == []


def test_invalid_coordinates_get_error_reply_no_emit():
    bot, messenger, sink = _bot()
    bot.handle(_msg("100.0 20.0 tank", ts=4))
    assert sink.emitted == []
    assert len(messenger.sent) == 1
    assert messenger.sent[0][1].startswith("❌")


def test_sender_not_on_allowlist_ignored():
    cfg = Config(signal_account=ACCOUNT, allowed_senders=(ACCOUNT,))
    bot, messenger, sink = _bot(cfg)
    bot.handle(_msg("48.5 39.8 tank", ts=5, source="+15550009999", destination=ACCOUNT))
    assert sink.emitted == []
    assert messenger.sent == []


def test_disallowed_sender_does_not_consume_dedup_slot():
    """A blocked sender's timestamp must not shadow a later allowed message."""
    cfg = Config(signal_account=ACCOUNT, allowed_senders=(ACCOUNT,))
    bot, messenger, sink = _bot(cfg)
    # blocked sender uses ts=99
    bot.handle(_msg("48.5 39.8 tank", ts=99, source="+15550009999"))
    # the account then legitimately uses the same ts=99 — must still be processed
    bot.handle(_msg("48.5 39.8 tank", ts=99, source=ACCOUNT, destination=ACCOUNT))
    assert len(sink.emitted) == 1


def test_second_allowed_sender_dm_replies_to_them():
    other = "+15551112222"
    cfg = Config(signal_account=ACCOUNT, allowed_senders=(ACCOUNT, other))
    bot, messenger, sink = _bot(cfg)
    bot.handle(_msg("48.5 39.8 tank", ts=6, source=other, destination=other, is_sync=False))
    assert len(sink.emitted) == 1
    assert messenger.sent[0][0] == other


def test_emit_failure_reports_error():
    bot, messenger, sink = _bot()
    sink.fail = True
    bot.handle(_msg("48.5 39.8 tank", ts=7))
    assert sink.emitted == []
    assert len(messenger.sent) == 1
    assert messenger.sent[0][1].startswith("❌")
    assert "TAK" in messenger.sent[0][1]


def test_reply_failure_does_not_raise():
    cfg = Config(signal_account=ACCOUNT, cot_url="log://stdout")

    class ExplodingMessenger(FakeMessenger):
        def send(self, recipient, text):
            raise RuntimeError("signal down")

    bot = Bot(cfg, ExplodingMessenger(), FakeSink())
    bot.handle(_msg("48.5 39.8 tank", ts=8))  # must not raise


@pytest.mark.parametrize("ts", [0, 0])
def test_zero_timestamp_not_treated_as_duplicate(ts):
    """ts=0 means 'unknown'; such messages must still be processed each time."""
    bot, messenger, sink = _bot()
    bot.handle(_msg("48.5 39.8 tank", ts=ts))
    bot.handle(_msg("48.6 39.9 truck", ts=ts))
    assert len(sink.emitted) == 2
