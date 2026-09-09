#!/usr/bin/env python3
"""Local CoT listener — a stand-in TAK client for testing without a phone.

Listens for CoT events over TCP and/or UDP (incl. multicast), prints a
one-line summary of each, and (re)writes a ``folium`` map so markers can
be eyeballed in a browser. This closes the whole Signal → CoT → TAK loop
on a laptop with no Android or iOS device in sight.

Usage::

    python tools/cot_listener.py                       # TCP :4242 + multicast 239.2.3.1:6969
    python tools/cot_listener.py --tcp 0.0.0.0:4242
    python tools/cot_listener.py --udp 239.2.3.1:6969  # multicast group auto-joined
    python tools/cot_listener.py --no-map              # console only

Point the bot at it with ``COT_URL=tcp://127.0.0.1:4242``.
"""

from __future__ import annotations

import argparse
import ipaddress
import logging
import socket
import struct
import sys
import threading
from pathlib import Path

# Make ``src`` importable when run straight from a checkout (no install needed).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from signal_atak.output.cot.encode import CotEvent, CotParseError, parse_cot  # noqa: E402

logger = logging.getLogger("cot_listener")

DEFAULT_TCP = "0.0.0.0:4242"
DEFAULT_UDP = "239.2.3.1:6969"
_RECV_BUF = 65535


def _split_hostport(value: str) -> tuple[str, int]:
    host, _, port = value.rpartition(":")
    if not host or not port.isdigit():
        raise argparse.ArgumentTypeError(f"expected host:port, got {value!r}")
    return host, int(port)


# CoT affiliation letter (type[2], e.g. a-h-G-…) → folium marker colour.
_AFFIL_COLOR = {"h": "red", "f": "blue", "n": "green", "s": "orange", "u": "gray"}


def _affiliation(cot_type: str) -> str:
    """The affiliation letter of a CoT type string (``a-h-G-…`` → ``h``)."""
    parts = cot_type.split("-")
    return parts[1] if len(parts) > 1 else "u"


class MapWriter:
    """Accumulates received events and rewrites an HTML map on each one.

    Markers are coloured by CoT affiliation (hostile red, friendly blue, …)
    and the view fits all points, so a whole scenario is visible at once.
    folium is imported lazily so the console-only path (``--no-map``) has
    no hard dependency on it.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._events: list[CotEvent] = []
        self._lock = threading.Lock()

    def add(self, event: CotEvent) -> None:
        """Add (or replace by uid) a marker and rewrite the map."""
        with self._lock:
            self._events = [e for e in self._events if e.uid != event.uid]
            self._events.append(event)
            self._render()
        logger.info("map updated → %s (%d marker(s))", self._path, len(self._events))

    def remove(self, target_uid: str) -> None:
        """Remove the marker with ``target_uid`` (a CoT delete) and rewrite the map."""
        with self._lock:
            before = len(self._events)
            self._events = [e for e in self._events if e.uid != target_uid]
            self._render()
        logger.info(
            "retracted %s → %s (%d marker(s))",
            target_uid,
            "removed" if len(self._events) < before else "not found",
            len(self._events),
        )

    def clear(self) -> None:
        """Drop all markers and write an empty map."""
        with self._lock:
            self._events = []
            self._render()
        logger.info("map cleared → %s", self._path)

    def _render(self) -> None:
        """Rewrite the HTML map from the current events (holds the lock)."""
        import folium

        if self._events:
            points = [(ev.lat, ev.lon) for ev in self._events]
            fmap = folium.Map(location=points[-1], zoom_start=11, tiles="OpenStreetMap")
            for ev in self._events:
                color = _AFFIL_COLOR.get(_affiliation(ev.type), "gray")
                folium.Marker(
                    location=(ev.lat, ev.lon),
                    popup=folium.Popup(
                        f"<b>{ev.callsign or ev.uid}</b><br>{ev.type}<br>{ev.remarks}",
                        max_width=260,
                    ),
                    tooltip=ev.callsign or ev.type,
                    icon=folium.Icon(color=color, icon="crosshairs", prefix="fa"),
                ).add_to(fmap)
            if len(points) > 1:
                fmap.fit_bounds(points, padding=(40, 40))
        else:
            fmap = folium.Map(location=(0, 0), zoom_start=2, tiles="OpenStreetMap")
        fmap.save(str(self._path))


def _handle(raw: bytes, source: str, mapwriter: MapWriter | None) -> None:
    """Parse one CoT payload and report it (add a marker, or honour a delete)."""
    try:
        event = parse_cot(raw)
    except CotParseError as exc:
        logger.warning("dropped non-CoT payload from %s: %s", source, exc)
        return
    if event.is_delete:
        logger.info("delete from %s | retract uid=%s", source, event.link_uid)
        if mapwriter is not None:
            mapwriter.remove(event.link_uid)
        return
    logger.info(
        "CoT from %s | type=%s lat=%s lon=%s callsign=%s",
        source,
        event.type,
        event.lat,
        event.lon,
        event.callsign,
    )
    if mapwriter is not None:
        mapwriter.add(event)


def _read_connection(conn: socket.socket, addr, mapwriter: MapWriter | None) -> None:
    """Drain one TCP connection to EOF and hand the payload to _handle.

    Runs in its own thread so a slow or idle client cannot block the
    accept loop, and guards its own socket errors (a peer RST raises
    ConnectionResetError) so one bad client cannot take down the server.
    """
    try:
        with conn:
            chunks = []
            while chunk := conn.recv(_RECV_BUF):
                chunks.append(chunk)
        _handle(b"".join(chunks), f"tcp {addr[0]}:{addr[1]}", mapwriter)
    except OSError as exc:
        logger.warning("tcp connection from %s:%s errored: %s", addr[0], addr[1], exc)


def _serve_tcp(host: str, port: int, mapwriter: MapWriter | None) -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(8)
    logger.info("TCP listening on %s:%s", host, port)
    while True:
        try:
            conn, addr = srv.accept()
        except OSError as exc:  # keep the listener alive across transient errors
            logger.warning("tcp accept failed: %s", exc)
            continue
        threading.Thread(target=_read_connection, args=(conn, addr, mapwriter), daemon=True).start()


def _serve_udp(host: str, port: int, mapwriter: MapWriter | None) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", port))
    if ipaddress.ip_address(host).is_multicast:
        mreq = struct.pack("4sl", socket.inet_aton(host), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        logger.info("UDP joined multicast %s:%s", host, port)
    else:
        logger.info("UDP listening on %s:%s", host, port)
    while True:
        try:
            raw, addr = sock.recvfrom(_RECV_BUF)
            _handle(raw, f"udp {addr[0]}:{addr[1]}", mapwriter)
        except OSError as exc:  # a transient recv error must not kill the thread
            logger.warning("udp recv failed: %s", exc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local CoT listener + folium map")
    parser.add_argument(
        "--tcp", type=_split_hostport, nargs="?", const=_split_hostport(DEFAULT_TCP)
    )
    parser.add_argument(
        "--udp", type=_split_hostport, nargs="?", const=_split_hostport(DEFAULT_UDP)
    )
    parser.add_argument("--map", default="cot_map.html", help="HTML map output path")
    parser.add_argument("--no-map", action="store_true", help="console only, skip the map")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Default: both transports if neither is named explicitly.
    tcp = args.tcp or (None if args.udp else _split_hostport(DEFAULT_TCP))
    udp = args.udp or (None if args.tcp else _split_hostport(DEFAULT_UDP))

    mapwriter = None if args.no_map else MapWriter(Path(args.map))

    threads: list[threading.Thread] = []
    if tcp:
        threads.append(threading.Thread(target=_serve_tcp, args=(*tcp, mapwriter), daemon=True))
    if udp:
        threads.append(threading.Thread(target=_serve_udp, args=(*udp, mapwriter), daemon=True))
    for t in threads:
        t.start()

    logger.info("listener ready — Ctrl-C to stop")
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        logger.info("shutting down")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
