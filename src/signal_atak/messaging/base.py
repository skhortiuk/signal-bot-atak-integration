"""The platform-neutral messaging contract.

Everything the bot needs from a chat backend is here; nothing in this
module knows about Signal, Telegram, or any specific service. A concrete
platform turns its own wire format into an :class:`InboundMessage` and
accepts plain ``(recipient, text)`` to send.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from attrs import field, frozen


@frozen
class InboundMessage:
    """A normalised inbound chat message, independent of platform.

    :param source: platform id of whoever sent the message (E.164 number,
        Telegram chat id, …).
    :param destination: who it was addressed to; the value to reply to.
        For a self-message (Note-to-Self) this equals ``source``.
    :param text: the message body.
    :param timestamp: a monotonic-ish platform timestamp used as the
        de-dup key (milliseconds where available).
    :param is_sync: ``True`` when the message reached us as an echo of the
        user's *own* sent message (Signal's Note-to-Self sync transcript)
        rather than a direct inbound. Platforms without the concept leave
        it ``False``.
    """

    source: str | None
    destination: str | None
    text: str
    timestamp: int
    is_sync: bool = field(default=False)


class Messenger(Protocol):
    """A chat backend the bot can receive from and reply through."""

    def send(self, recipient: str, text: str) -> None:
        """Send ``text`` to ``recipient`` on this platform."""
        ...

    def receive(self) -> Iterator[InboundMessage]:
        """Yield normalised inbound messages, blocking until the stream ends."""
        ...
