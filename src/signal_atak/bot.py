"""The bot: receive → parse → emit to a sink → reply on the chat platform.

The bot is platform- and output-agnostic: it depends only on the
:class:`~signal_atak.messaging.base.Messenger` and
:class:`~signal_atak.output.base.Sink` protocols, never on Signal or CoT
directly. :meth:`Bot.handle` processes exactly one message and is pure
w.r.t. the network (it only calls the injected collaborators), so it is
tested with a fake messenger and a fake sink.

Loop avoidance
--------------
The bot may run on a linked device whose own outgoing replies come back to
it (Signal's Note-to-Self sync transcripts). Three guards stop it reacting
to itself:

1. Replies never look like a coordinate message, so :func:`parse_target`
   returns ``None`` for them and they are ignored.
2. Messages are de-duplicated by their platform timestamp.
3. Only senders on the allow-list (default: the bot's own account) are
   acted on.
"""

from __future__ import annotations

import logging
import time
from collections import deque

from .config import Config
from .messaging.base import InboundMessage, Messenger
from .output.base import Sink
from .parser import InvalidCoordinateError, parse_target

logger = logging.getLogger(__name__)

_OK = "✅"
_ERR = "❌"


class _SeenTimestamps:
    """Bounded de-dup set: remembers the last ``maxlen`` message timestamps."""

    def __init__(self, maxlen: int = 512) -> None:
        self._order: deque[int] = deque(maxlen=maxlen)
        self._set: set[int] = set()

    def seen(self, ts: int) -> bool:
        """Record ``ts``; return whether it had already been seen."""
        if ts in self._set:
            return True
        if len(self._order) == self._order.maxlen:
            self._set.discard(self._order[0])  # evict the oldest before it drops off
        self._order.append(ts)
        self._set.add(ts)
        return False


class Bot:
    """Wires a :class:`Messenger` to a :class:`Sink` under a :class:`Config`."""

    def __init__(self, config: Config, messenger: Messenger, sink: Sink) -> None:
        self._config = config
        self._messenger = messenger
        self._sink = sink
        self._seen = _SeenTimestamps()

    def handle(self, message: InboundMessage) -> None:
        """Process a single inbound message end-to-end."""
        # Allow-list first, so disallowed senders never consume a de-dup slot.
        if not self._config.sender_allowed(message.source):
            logger.debug("skip sender not on allow-list: %s", message.source)
            return

        reply_to = message.destination or message.source
        try:
            target = parse_target(message.text, lon_first=self._config.lon_first)
        except InvalidCoordinateError as exc:
            logger.info("invalid coordinates from %s: %s", message.source, exc)
            self._reply(reply_to, f"{_ERR} {exc}")
            return

        if target is None:
            return  # ordinary chatter (or our own reply) — stay silent

        # De-dup only messages we are actually about to act on, and only once
        # a real target is in hand — recorded here so a redelivery of the same
        # message (same timestamp) is not emitted twice.
        if message.timestamp and self._seen.seen(message.timestamp):
            logger.debug("skip duplicate ts=%s", message.timestamp)
            return

        try:
            self._sink.emit(target)
        except OSError as exc:
            logger.error("emit to sink failed: %s", exc)
            self._reply(reply_to, f"{_ERR} Could not deliver to TAK: {exc}")
            return

        logger.info(
            "emitted %s (%s, %s) → %s",
            target.description,
            target.lat,
            target.lon,
            self._config.cot_url,
        )
        # "sent" is honest for best-effort transports (UDP/multicast cannot
        # confirm receipt); we do not claim the client actually displayed it.
        where = self._config.cot_url
        self._reply(
            reply_to,
            f"{_OK} sent {target.description} @ {target.lat}, {target.lon} → {where}",
        )

    def _reply(self, recipient: str | None, text: str) -> None:
        """Best-effort reply; a failed reply must not kill the loop."""
        if not recipient:
            return
        try:
            self._messenger.send(recipient, text)
        except Exception:  # noqa: BLE001 - reply failures are non-fatal
            logger.exception("failed to send reply to %s", recipient)

    def run(self, *, reconnect_delay: float = 3.0) -> None:
        """Consume the receive stream forever, reconnecting on drop."""
        logger.info(
            "bot up: platform=%s account=%s cot_url=%s allow=%s",
            self._config.messaging_platform,
            self._config.signal_account,
            self._config.cot_url,
            self._config.allowed_senders or (self._config.signal_account,),
        )
        while True:
            try:
                for message in self._messenger.receive():
                    self.handle(message)
                # A clean end of stream is still a disconnect — say so, then reconnect.
                logger.info("receive stream ended; reconnecting in %ss", reconnect_delay)
            except KeyboardInterrupt:
                logger.info("shutting down")
                return
            except Exception:  # noqa: BLE001 - keep the daemon alive; log with traceback
                logger.exception("receive loop error; reconnecting in %ss", reconnect_delay)
            time.sleep(reconnect_delay)
