"""The output contract: a :class:`Sink` consumes a parsed :class:`Target`.

This is the seam that keeps ``bot.py`` free of any CoT/ATAK knowledge.
The bot parses a message into a :class:`~signal_atak.parser.Target` and
hands it to ``sink.emit``; how the target becomes an on-the-wire event
(CoT XML today, something else tomorrow) lives entirely behind here.
"""

from __future__ import annotations

from typing import Protocol

from ..parser import Target


class Sink(Protocol):
    """A destination for parsed targets."""

    def emit(self, target: Target) -> None:
        """Encode and deliver ``target``.

        :raises OSError: on a transport-level delivery failure (the bot
            catches this to report it back to the user).
        """
        ...

    def close(self) -> None:
        """Release any held resources (sockets, files)."""
        ...
