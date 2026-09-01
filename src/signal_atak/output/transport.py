"""Byte transports for delivering an encoded event to a ``COT_URL``.

A transport is format-agnostic: it moves bytes to a destination described
by a URL. The CoT sink builds the bytes; the transport just ships them.

Supported schemes:

===================================  =========================================
``log://stdout``                     print the payload (protocol proof / CI)
``tcp://<host>:<port>``              a TCP stream (e.g. an iTAK/WinTAK input
                                     or the bundled ``cot_listener``)
``udp://<host>:<port>``              UDP unicast, or **multicast** when the
                                     host is in 224.0.0.0/4 (ATAK/iTAK SA mesh
                                     default is ``udp://239.2.3.1:6969``)
===================================  =========================================

The brief suggests ``pytak``. This module uses stdlib ``socket`` instead:
sending one event per message needs a few lines, whereas pytak's asyncio
``CLITool``/``QueueWorker`` model is built for continuous CoT streams and
adds an event loop and queue plumbing we would only work around. The
trade-off is written up in ``docs/challenges.md``. The interface here
(:func:`build_transport` returning something with ``.send(bytes)``) keeps
the choice swappable.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import struct
import sys
from typing import Protocol
from urllib.parse import urlparse

from attrs import field, frozen

logger = logging.getLogger(__name__)

#: default TTL for multicast so events cross the local switch but not the internet
_MULTICAST_TTL = 1


class Transport(Protocol):
    """Anything that can deliver a byte payload and be closed."""

    def send(self, payload: bytes) -> None: ...

    def close(self) -> None: ...


@frozen
class CotUrl:
    """A parsed ``COT_URL``.

    Kept as an object (not a bare tuple/dict) so callers pass one typed
    value around and validation lives in one place.
    """

    scheme: str = field()
    host: str = ""
    port: int = 0

    @classmethod
    def parse(cls, url: str) -> CotUrl:
        """Parse ``url`` into a :class:`CotUrl`.

        :raises ValueError: on an unknown scheme or a missing host/port
            for the network schemes.
        """
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if scheme == "log":
            # log://stdout — netloc is the sink name; only stdout is supported
            if parsed.netloc not in ("stdout", ""):
                raise ValueError(f"Only 'log://stdout' is supported, got {url!r}")
            return cls(scheme="log")
        if scheme in ("tcp", "udp"):
            if not parsed.hostname or not parsed.port:
                raise ValueError(f"{scheme} URL needs host and port, got {url!r}")
            return cls(scheme=scheme, host=parsed.hostname, port=parsed.port)
        raise ValueError(f"Unsupported COT_URL scheme {scheme!r} in {url!r}")

    @property
    def is_multicast(self) -> bool:
        """True when the host is an IPv4/IPv6 multicast address."""
        try:
            return ipaddress.ip_address(self.host).is_multicast
        except ValueError:
            return False


class StdoutTransport:
    """Writes the payload to stdout. Used for protocol proof and CI."""

    def send(self, payload: bytes) -> None:
        sys.stdout.write(payload.decode("utf-8") + "\n")
        sys.stdout.flush()

    def close(self) -> None:  # noqa: D102 - nothing to release
        pass


class UdpTransport:
    """Sends each payload as one UDP datagram (unicast or multicast).

    A fresh socket per instance is cheap and avoids sharing state across
    threads; multicast sets an explicit TTL so packets are not dropped or,
    conversely, flooded beyond the local segment.
    """

    def __init__(self, url: CotUrl) -> None:
        self._addr = (url.host, url.port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if url.is_multicast:
            self._sock.setsockopt(
                socket.IPPROTO_IP,
                socket.IP_MULTICAST_TTL,
                struct.pack("b", _MULTICAST_TTL),
            )
        logger.info("UDP transport → %s:%s (multicast=%s)", *self._addr, url.is_multicast)

    def send(self, payload: bytes) -> None:
        self._sock.sendto(payload, self._addr)

    def close(self) -> None:
        self._sock.close()


class TcpTransport:
    """Sends each payload over its own short-lived TCP connection.

    One connection per event is the most interoperable choice for legacy
    CoT inputs: the receiver reads until EOF and gets exactly one
    document, so no message framing has to be agreed. It costs a TCP
    handshake per marker, negligible at human message rates.
    """

    def __init__(self, url: CotUrl, *, timeout: float = 5.0) -> None:
        self._addr = (url.host, url.port)
        self._timeout = timeout
        logger.info("TCP transport → %s:%s", *self._addr)

    def send(self, payload: bytes) -> None:
        with socket.create_connection(self._addr, timeout=self._timeout) as sock:
            sock.sendall(payload)

    def close(self) -> None:  # noqa: D102 - connections are per-send
        pass


def build_transport(cot_url: str) -> Transport:
    """Construct the right :class:`Transport` for ``cot_url``.

    :raises ValueError: propagated from :meth:`CotUrl.parse` on a bad URL.
    """
    url = CotUrl.parse(cot_url)
    if url.scheme == "log":
        return StdoutTransport()
    if url.scheme == "udp":
        return UdpTransport(url)
    if url.scheme == "tcp":
        return TcpTransport(url)
    raise ValueError(f"No transport for scheme {url.scheme!r}")  # pragma: no cover
