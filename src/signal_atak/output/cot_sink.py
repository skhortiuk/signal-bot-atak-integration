"""The default sink: encode a Target as Cursor-on-Target, ship it on a transport.

This is where the two halves of "output" meet — the CoT *encoding*
(:func:`~signal_atak.output.cot.encode.build_cot`) and the byte
*transport* (:mod:`~signal_atak.output.transport`). The bot sees only the
:class:`~signal_atak.output.base.Sink` interface, so swapping either half
(a different format, a different wire) does not touch the bot.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from ..parser import Target
from .cot.encode import build_cot
from .transport import Transport

logger = logging.getLogger(__name__)


class CotSink:
    """Encodes each target as CoT XML and sends it over ``transport``.

    :param transport: the byte transport (udp/tcp/log).
    :param affiliation: CoT affiliation letter baked into every event.
    :param stale_minutes: marker lifetime written into every event.
    :param state_path: if set, every emitted marker's uid is appended here
        (one per line) so ``tools/clear_map.py`` can later retract them.
    """

    def __init__(
        self,
        transport: Transport,
        *,
        affiliation: str = "h",
        stale_minutes: float = 10.0,
        state_path: Path | None = None,
    ) -> None:
        self._transport = transport
        self._affiliation = affiliation
        self._stale_minutes = stale_minutes
        self._state_path = state_path

    def emit(self, target: Target) -> None:
        """Encode ``target`` as CoT and hand the bytes to the transport.

        :raises OSError: propagated from the transport on a delivery failure.
        """
        marker_uid = f"signal-{uuid.uuid4()}"
        cot_xml = build_cot(
            target,
            affiliation=self._affiliation,
            stale_minutes=self._stale_minutes,
            uid=marker_uid,
        )
        self._transport.send(cot_xml)
        self._record(marker_uid)

    def _record(self, marker_uid: str) -> None:
        """Append an emitted uid to the state file; never fatal on failure."""
        if self._state_path is None:
            return
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            with self._state_path.open("a", encoding="utf-8") as fh:
                fh.write(marker_uid + "\n")
        except OSError as exc:  # tracking is best-effort, never break delivery
            logger.warning("could not record uid to %s: %s", self._state_path, exc)

    def close(self) -> None:
        self._transport.close()
