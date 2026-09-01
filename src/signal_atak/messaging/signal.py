"""Signal platform via signal-cli's HTTP JSON-RPC daemon (0.14.x).

Start the daemon out-of-band::

    signal-cli -a +YOURNUMBER daemon --http=127.0.0.1:8080 --receive-mode=on-connection

``--receive-mode=on-connection`` matters: signal-cli's default (``on-start``)
pulls and acks messages from the Signal servers continuously, but the HTTP
``/api/v1/events`` handler is only attached while an SSE client is connected
and there is no replay. So any message that arrives while the bot is
reconnecting (or down) would be acked to nobody and lost. ``on-connection``
makes the daemon pull only while a client is attached, so messages queue
server-side across disconnects.

It exposes three endpoints (verified against the 0.14.x man page / source):

* ``POST /api/v1/rpc``    — a single or batch JSON-RPC request (used for ``send``)
* ``GET  /api/v1/events`` — a Server-Sent Events stream of incoming messages
* ``GET  /api/v1/check``  — 200 OK liveness probe

The Note-to-Self path
---------------------
Because the bot is a *linked* (secondary) device and the user tests by
messaging themselves, their messages do NOT arrive as ordinary
``dataMessage`` events — the primary phone reports what it sent as a
**sync transcript** under ``envelope.syncMessage.sentMessage``.
:func:`normalize_envelope` extracts the text from BOTH shapes, which is
the single most important detail in this integration.

Testability
-----------
The two things worth getting right are the pure functions
:func:`parse_sse_stream` (SSE framing) and :func:`normalize_envelope`
(envelope shapes); both are unit-tested without a network.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Iterator
from urllib import request

from .base import InboundMessage

logger = logging.getLogger(__name__)

#: short timeout for the request/response RPC calls (send, check) — a local
#: daemon answers in milliseconds; anything longer means it is wedged and we
#: must surface it rather than block the single receive+reply thread forever.
_RPC_TIMEOUT = 10.0

#: read timeout for the long-lived SSE stream. signal-cli sends ``:`` keep-alive
#: comments, so no data at all for this long means a dead/half-open connection;
#: raising here lets ``bot.run`` reconnect instead of hanging.
_SSE_TIMEOUT = 120.0


class SignalRpcError(RuntimeError):
    """A JSON-RPC call returned an ``error`` object or the daemon was unreachable."""


# --------------------------------------------------------------------------- #
# Pure helpers (no I/O) — the parts worth unit-testing thoroughly.
# --------------------------------------------------------------------------- #
def parse_sse_stream(lines: Iterable[str]) -> Iterator[dict]:
    """Yield the JSON payload of each ``data:`` field in an SSE ``lines`` stream.

    Implements the subset of the SSE grammar signal-cli emits: ``event:``
    and ``data:`` fields, blank line = dispatch, ``:`` comment =
    keep-alive. Multiple ``data:`` lines in one event are joined with
    newlines per the spec. Non-JSON data payloads are skipped with a warning.
    """
    data_parts: list[str] = []
    for raw in lines:
        line = raw.rstrip("\n").rstrip("\r")
        if line == "":  # dispatch the buffered event
            if data_parts:
                yield from _decode_sse_data("\n".join(data_parts))
                data_parts = []
            continue
        if line.startswith(":"):  # comment / keep-alive
            continue
        field_name, _, value = line.partition(":")
        if value.startswith(" "):  # SSE allows one optional leading space
            value = value[1:]
        if field_name == "data":
            data_parts.append(value)
        # 'event', 'id', 'retry' fields are ignored: we only need the payload
    if data_parts:  # stream ended without a trailing blank line
        yield from _decode_sse_data("\n".join(data_parts))


def _decode_sse_data(blob: str) -> Iterator[dict]:
    try:
        yield json.loads(blob)
    except json.JSONDecodeError:
        logger.warning("Skipping non-JSON SSE data payload: %.80r", blob)


def _find_envelope(payload: dict) -> dict | None:
    """Locate the ``envelope`` object across signal-cli's wrapper variants.

    * SSE / ``JsonReceiveMessageHandler``: ``{"account", "envelope"}``
    * auto-receive JSON-RPC notification: ``params.envelope``
    * subscribeReceive notification: ``params.result.envelope``
    """
    if "envelope" in payload:
        return payload["envelope"]
    params = payload.get("params")
    if isinstance(params, dict):
        if "envelope" in params:
            return params["envelope"]
        result = params.get("result")
        if isinstance(result, dict) and "envelope" in result:
            return result["envelope"]
    return None


def normalize_envelope(payload: dict) -> InboundMessage | None:
    """Turn a raw signal-cli receive payload into an :class:`InboundMessage`.

    Returns ``None`` for anything that is not a text-bearing message
    (receipts, typing indicators, empty envelopes) — the caller must stay
    silent on those.
    """
    envelope = _find_envelope(payload)
    if envelope is None:
        return None

    source = envelope.get("source") or envelope.get("sourceNumber")
    timestamp = int(envelope.get("timestamp", 0))

    data_message = envelope.get("dataMessage")
    if isinstance(data_message, dict) and data_message.get("message"):
        return InboundMessage(
            source=source,
            destination=source,  # a direct message is addressed to us
            text=data_message["message"],
            timestamp=int(data_message.get("timestamp", timestamp)),
            is_sync=False,
        )

    sync = envelope.get("syncMessage")
    if isinstance(sync, dict):
        sent = sync.get("sentMessage")
        if isinstance(sent, dict) and sent.get("message"):
            return InboundMessage(
                source=source,
                destination=sent.get("destination") or sent.get("destinationNumber"),
                text=sent["message"],
                timestamp=int(sent.get("timestamp", timestamp)),
                is_sync=True,
            )
    return None


# --------------------------------------------------------------------------- #
# Concrete HTTP client
# --------------------------------------------------------------------------- #
class SignalClient:
    """Talks to a running ``signal-cli`` HTTP daemon. Implements ``Messenger``.

    :param account: the bot's own E.164 number (the ``-a`` the daemon runs with).
    :param http: ``host:port`` the daemon's ``--http`` listens on.
    """

    def __init__(self, account: str, http: str = "127.0.0.1:8080") -> None:
        self._account = account
        self._base = f"http://{http}/api/v1"
        self._id = 0

    def send(self, recipient: str, text: str) -> None:
        """Send ``text`` to ``recipient`` (E.164) via the ``send`` JSON-RPC method.

        :raises SignalRpcError: on a JSON-RPC error or an unreachable daemon.
        """
        result = self._rpc("send", {"recipient": [recipient], "message": text})
        logger.info("sent to %s (server ts=%s)", recipient, result.get("timestamp"))

    def receive(self) -> Iterator[InboundMessage]:
        """Yield normalised inbound messages from the SSE event stream.

        Blocks, streaming until the connection drops; the caller
        (``bot.py``) is responsible for reconnecting.

        :raises SignalRpcError: if the events endpoint cannot be opened.
        """
        url = f"{self._base}/events"
        try:
            response = request.urlopen(url, timeout=_SSE_TIMEOUT)  # noqa: S310 - localhost daemon
        except OSError as exc:  # URLError, socket timeout, connection refused
            raise SignalRpcError(f"cannot open events stream at {url}: {exc}") from exc

        with response:
            lines = (raw.decode("utf-8") for raw in response)
            for payload in parse_sse_stream(lines):
                if "exception" in payload:
                    logger.warning("signal-cli receive exception: %s", payload["exception"])
                message = normalize_envelope(payload)
                if message is not None:
                    yield message

    def check(self) -> bool:
        """Liveness probe against ``/api/v1/check`` (200 = daemon up)."""
        try:
            with request.urlopen(f"{self._base}/check", timeout=_RPC_TIMEOUT) as resp:  # noqa: S310
                return resp.status == 200
        except OSError:
            return False

    def _rpc(self, method: str, params: dict) -> dict:
        self._id += 1
        body = json.dumps(
            {"jsonrpc": "2.0", "method": method, "params": params, "id": self._id}
        ).encode("utf-8")
        req = request.Request(
            f"{self._base}/rpc",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(
                req, timeout=_RPC_TIMEOUT
            ) as resp:  # noqa: S310 - localhost daemon
                response = json.loads(resp.read().decode("utf-8"))
        except OSError as exc:  # URLError, socket.timeout (a wedged daemon), refused
            raise SignalRpcError(f"{method} request to daemon failed: {exc}") from exc

        if "error" in response:
            raise SignalRpcError(f"{method} returned error: {response['error']}")
        return response.get("result", {})
