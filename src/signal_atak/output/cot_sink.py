"""The default sink: encode a Target as Cursor-on-Target, ship it on a transport.

This is where the two halves of "output" meet — the CoT *encoding*
(:func:`~signal_atak.output.cot.encode.build_cot`) and the byte
*transport* (:mod:`~signal_atak.output.transport`). The bot sees only the
:class:`~signal_atak.output.base.Sink` interface, so swapping either half
(a different format, a different wire) does not touch the bot.
"""

from __future__ import annotations

from ..parser import Target
from .cot.encode import build_cot
from .transport import Transport


class CotSink:
    """Encodes each target as CoT XML and sends it over ``transport``.

    :param transport: the byte transport (udp/tcp/log).
    :param affiliation: CoT affiliation letter baked into every event.
    :param stale_minutes: marker lifetime written into every event.
    """

    def __init__(
        self,
        transport: Transport,
        *,
        affiliation: str = "h",
        stale_minutes: float = 10.0,
    ) -> None:
        self._transport = transport
        self._affiliation = affiliation
        self._stale_minutes = stale_minutes

    def emit(self, target: Target) -> None:
        """Encode ``target`` as CoT and hand the bytes to the transport.

        :raises OSError: propagated from the transport on a delivery failure.
        """
        cot_xml = build_cot(
            target,
            affiliation=self._affiliation,
            stale_minutes=self._stale_minutes,
        )
        self._transport.send(cot_xml)

    def close(self) -> None:
        self._transport.close()
