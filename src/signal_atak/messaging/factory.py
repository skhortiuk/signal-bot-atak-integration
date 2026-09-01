"""Messenger registry — map a platform name to a constructor.

Adding a platform is one entry here plus its module; nothing else in the
codebase changes. ``bot.py`` and ``__main__.py`` call
:func:`build_messenger` and stay platform-agnostic.
"""

from __future__ import annotations

from collections.abc import Callable

from ..config import Config
from .base import Messenger
from .signal import SignalClient

#: platform name → factory that builds a Messenger from Config
_REGISTRY: dict[str, Callable[[Config], Messenger]] = {
    "signal": lambda cfg: SignalClient(cfg.signal_account, cfg.signal_http),
}


def available_platforms() -> tuple[str, ...]:
    """Names accepted by :func:`build_messenger`."""
    return tuple(_REGISTRY)


def build_messenger(config: Config) -> Messenger:
    """Construct the Messenger for ``config.messaging_platform``.

    :raises ValueError: on an unknown platform name.
    """
    try:
        factory = _REGISTRY[config.messaging_platform]
    except KeyError:
        raise ValueError(
            f"Unknown messaging platform {config.messaging_platform!r}; "
            f"available: {', '.join(available_platforms())}"
        ) from None
    return factory(config)
