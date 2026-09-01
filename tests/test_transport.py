"""Tests for :mod:`signal_atak.output.transport` (URL parsing + stdout + live loopback)."""

from __future__ import annotations

import socket
import threading

import pytest

from signal_atak.output.transport import (
    CotUrl,
    StdoutTransport,
    build_transport,
)


def test_parse_log_url():
    url = CotUrl.parse("log://stdout")
    assert url.scheme == "log"


def test_parse_tcp_url():
    url = CotUrl.parse("tcp://127.0.0.1:4242")
    assert (url.scheme, url.host, url.port) == ("tcp", "127.0.0.1", 4242)


def test_parse_udp_multicast_flagged():
    assert CotUrl.parse("udp://239.2.3.1:6969").is_multicast is True
    assert CotUrl.parse("udp://127.0.0.1:6969").is_multicast is False


@pytest.mark.parametrize(
    "bad",
    ["ftp://x:1", "tcp://nohost", "tcp://host", "log://somewhere"],
)
def test_bad_urls_raise(bad):
    with pytest.raises(ValueError):
        CotUrl.parse(bad)


def test_build_transport_dispatch():
    assert isinstance(build_transport("log://stdout"), StdoutTransport)
    build_transport("tcp://127.0.0.1:4242").close()
    build_transport("udp://239.2.3.1:6969").close()


def test_stdout_transport_writes(capsys):
    StdoutTransport().send(b"<event/>")
    assert "<event/>" in capsys.readouterr().out


def test_tcp_transport_loopback_delivers_bytes():
    """Live check: TcpTransport bytes arrive intact at a real socket."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    received: list[bytes] = []

    def accept_once():
        conn, _ = srv.accept()
        with conn:
            chunks = []
            while chunk := conn.recv(4096):
                chunks.append(chunk)
        received.append(b"".join(chunks))

    t = threading.Thread(target=accept_once)
    t.start()

    transport = build_transport(f"tcp://127.0.0.1:{port}")
    transport.send(b"<event version='2.0'/>")
    transport.close()
    t.join(timeout=5)
    srv.close()

    assert received == [b"<event version='2.0'/>"]
