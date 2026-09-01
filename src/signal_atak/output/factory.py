"""Sink registry — map an output name to a constructor.

Adding an output format (GeoJSON, KML, a TAK-Server client, …) is one
entry here plus its module; ``bot.py`` calls :func:`build_sink` and stays
output-agnostic.
"""

from __future__ import annotations

from collections.abc import Callable

from ..config import Config
from .base import Sink
from .cot_sink import CotSink
from .transport import build_transport


def _build_cot_sink(cfg: Config) -> Sink:
    return CotSink(
        build_transport(cfg.cot_url),
        affiliation=cfg.affiliation,
        stale_minutes=cfg.stale_minutes,
    )


#: output name → factory that builds a Sink from Config
_REGISTRY: dict[str, Callable[[Config], Sink]] = {
    "cot": _build_cot_sink,
}


def available_sinks() -> tuple[str, ...]:
    """Names accepted by :func:`build_sink`."""
    return tuple(_REGISTRY)


def build_sink(config: Config) -> Sink:
    """Construct the Sink for ``config.output_sink``.

    :raises ValueError: on an unknown sink name, or from the transport
        layer on a bad ``COT_URL``.
    """
    try:
        factory = _REGISTRY[config.output_sink]
    except KeyError:
        raise ValueError(
            f"Unknown output sink {config.output_sink!r}; available: {', '.join(available_sinks())}"
        ) from None
    return factory(config)
