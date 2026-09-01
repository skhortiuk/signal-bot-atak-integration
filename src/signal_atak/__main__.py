"""Entrypoint: ``python -m signal_atak``.

Loads config, builds the messaging platform and the output sink from their
registries, and runs the bot loop. All configuration comes from the
environment / ``.env`` (see :mod:`signal_atak.config`).
"""

from __future__ import annotations

import logging
import sys

from .bot import Bot
from .config import load_config
from .messaging.factory import build_messenger
from .messaging.signal import SignalClient
from .output.factory import build_sink


def main() -> int:
    config = load_config()
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("signal_atak")

    try:
        sink = build_sink(config)
    except ValueError as exc:
        log.error("bad output config: %s", exc)
        return 2

    try:
        messenger = build_messenger(config)
    except ValueError as exc:
        log.error("bad messaging config: %s", exc)
        sink.close()
        return 2

    # The Signal backend can probe its daemon; give a precise hint if it is down.
    if isinstance(messenger, SignalClient) and not messenger.check():
        log.error(
            "signal-cli daemon not reachable at %s. Start it with:\n"
            "  signal-cli -a %s daemon --http=%s --receive-mode=on-connection",
            config.signal_http,
            config.signal_account,
            config.signal_http,
        )
        sink.close()
        return 3

    try:
        Bot(config, messenger, sink).run()
    finally:
        sink.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
