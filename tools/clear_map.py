#!/usr/bin/env python3
"""Retract every marker the bot has sent — clear the map before a recording.

The bot appends each emitted marker's uid to a state file (see
``Config.state_file``, default in the OS temp dir). This tool reads those
uids and sends a CoT *delete* event for each to a ``COT_URL``, which tells
ATAK / iTAK / WinTAK — and the bundled ``cot_listener`` — to remove the
markers. It then truncates the state file.

Usage::

    python tools/clear_map.py                                   # defaults: multicast + temp state
    python tools/clear_map.py --cot-url tcp://192.168.1.50:4242 # to an iTAK TCP input
    python tools/clear_map.py --map cot_map.html               # also blank a listener map file

Point it at the SAME ``COT_URL`` the bot used so the deletes reach the
same client.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Make ``src`` importable when run straight from a checkout (no install needed).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from signal_atak.config import DEFAULT_STATE_FILE  # noqa: E402
from signal_atak.output.cot.encode import build_delete_cot  # noqa: E402
from signal_atak.output.transport import build_transport  # noqa: E402

logger = logging.getLogger("clear_map")


def _read_uids(state: Path) -> list[str]:
    """Read unique, order-preserving marker uids from the state file."""
    if not state.is_file():
        return []
    seen: dict[str, None] = {}
    for line in state.read_text(encoding="utf-8").splitlines():
        uid = line.strip()
        if uid:
            seen.setdefault(uid, None)
    return list(seen)


def _blank_map(path: Path) -> None:
    """Write an empty folium map (for when no listener is running to clear itself)."""
    import folium

    folium.Map(location=(0, 0), zoom_start=2, tiles="OpenStreetMap").save(str(path))
    logger.info("blanked map → %s", path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retract emitted CoT markers")
    parser.add_argument("--cot-url", default="udp://239.2.3.1:6969", help="where to send deletes")
    parser.add_argument("--state", default=DEFAULT_STATE_FILE, help="emitted-uid state file")
    parser.add_argument("--map", help="also blank this listener map file")
    parser.add_argument("--keep-state", action="store_true", help="do not truncate the state file")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    state = Path(args.state)
    uids = _read_uids(state)
    if not uids:
        logger.info("no emitted markers to retract (state file %s empty/absent)", state)
    else:
        transport = build_transport(args.cot_url)
        try:
            for uid in uids:
                transport.send(build_delete_cot(uid))
        finally:
            transport.close()
        logger.info("sent %d delete(s) → %s", len(uids), args.cot_url)
        if not args.keep_state:
            state.write_text("", encoding="utf-8")
            logger.info("cleared state file %s", state)

    if args.map:
        _blank_map(Path(args.map))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
