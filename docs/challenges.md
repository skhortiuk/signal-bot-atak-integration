# Challenges & decisions

The real problems this integration ran into, and how each was resolved.

## 1. Note-to-Self messages arrive as sync transcripts, not incoming messages

**The problem.** The bot runs on a *linked* (secondary) Signal device, and it is
tested by the user messaging themselves (Note-to-Self). A linked device does not
receive the user's own messages as ordinary `dataMessage` events. Instead, the
primary phone tells its linked devices *what it just sent* — a **sync transcript**
— delivered under `envelope.syncMessage.sentMessage`. A bot that only looks at
`envelope.dataMessage.message` sees nothing and appears dead, even though
signal-cli is receiving fine.

**The fix.** `messaging/signal.py`'s `normalize_envelope` extracts the body from
**both** shapes and yields a single `InboundMessage(source, destination, text,
timestamp, is_sync)`:

- direct message: `envelope.dataMessage.message`, sender from `envelope.source`;
- sync transcript: `envelope.syncMessage.sentMessage.message`, recipient from
  `sentMessage.destination`.

The exact field names were verified against the signal-cli 0.14.x man page
(`syncMessage.sentMessage` with `destination`/`destinationNumber`), not guessed.
The normaliser also unwraps the two JSON-RPC wrapper variants (`params.envelope`
and the `subscribeReceive` form `params.result.envelope`) so it works over the
HTTP SSE stream and the raw JSON-RPC transports alike.

## 2. The bot sees its own replies → feedback-loop risk

**The problem.** Because sending to yourself also produces a sync transcript, the
bot's own `✅ sent…` reply comes straight back to it. Naively, that could be
re-processed forever.

**The fix.** Three independent guards (`bot.py`):
1. **Pattern filter** — a reply never matches the coordinate regex, so
   `parse_target` returns `None` and the message is ignored. This is the primary
   guard and it alone breaks the loop.
2. **Timestamp de-dup** — a bounded `_SeenTimestamps` set drops any message whose
   signal-cli timestamp was already handled (redelivery on reconnect, echoes).
3. **Sender allow-list** — only configured numbers (default: the bot's own
   account) are acted on.

The `test_does_not_loop_on_its_own_reply` test feeds a reply back in as a fresh
transcript and asserts zero additional CoT sends.

## 3. signal-cli version drift

**The problem.** The brief assumed signal-cli ~0.13.x. The current release is
0.14.7; the last 0.13.x (0.13.24, Feb 2026) is already past Signal-Server's
~3-month compatibility window and will simply stop authenticating. 0.14.0 also
made two breaking changes that affect us: `daemon` now *requires* a channel flag
(`--http`/`--socket`/`--tcp`), and `link` prints the QR in the terminal itself
(no more piping to `qrencode`).

**The fix.** Build against 0.14.x. The README pins the install to a current
signal-cli and documents the `--http` daemon invocation and the in-terminal QR.

## 4. `pytak` vs. stdlib sockets

**The problem.** The brief suggests `pytak` for CoT delivery. `pytak` is built
around an asyncio `CLITool` + `QueueWorker` model designed for *continuous* CoT
streams: you subclass workers, run an event loop, and push events through a
queue. For a bot that emits one event per human message, that is a lot of
machinery — and mixing an always-on asyncio loop into an otherwise synchronous
receive loop adds a failure surface with no upside here.

**The fix.** A small `output/transport.py` over stdlib `socket` covers every
scheme the assignment needs — `log://stdout`, `tcp://`, `udp://` including
multicast (with an explicit `IP_MULTICAST_TTL`). The public surface is a
`build_transport(url) → object with .send(bytes)` factory wrapped by `CotSink`,
so the choice is swappable: dropping in a pytak-backed transport later touches
nothing in `bot.py`. The trade-off: we don't get pytak's TLS/TAK-Server
transports for free — acceptable, since the demo targets iTAK/WinTAK inputs and
the local listener, not a TAK Server.

## 5. Multicast is unreliable on consumer Wi-Fi

**The problem.** `udp://239.2.3.1:6969` is the ATAK/iTAK SA mesh default and often
works with zero client config — but plenty of consumer routers drop multicast
(IGMP snooping, AP/client isolation), so the marker silently never arrives.

**The fix.** Support both and document both. Multicast is the default (least
setup when it works); TCP unicast (`tcp://<device_ip>:<port>` with a manually
added iTAK input) is the reliable fallback that crosses those routers. The bundled
`cot_listener.py` speaks both so the whole chain can be proven locally regardless.

## 6. Parsing untrusted XML safely

**The problem.** The listener parses CoT XML arriving over the network. Python's
stdlib XML parser is vulnerable to XXE (external entity) and billion-laughs
expansion attacks on hostile input.

**The fix.** `cot.parse_cot` uses `defusedxml` for the parse path
(`test_xxe_entity_is_not_expanded` asserts a malicious entity is rejected).
*Building* XML with stdlib `ElementTree` is not a parse and is unaffected.

## 7. Lost messages across reconnects (`--receive-mode`)

**The problem.** An adversarial review of the code surfaced a silent data-loss
bug that has nothing to do with our Python: signal-cli's default
`--receive-mode=on-start` pulls and *acknowledges* messages from Signal's
servers continuously from daemon startup. But the HTTP `/api/v1/events` handler
is only attached while an SSE client is connected, and there is no replay
(events are sent with no id, so no `Last-Event-ID` catch-up). Any message that
arrives while the bot is between reconnects — or before it first connects, or
during a redeploy — is acked to nobody and never re-delivered. The coordinate
silently never reaches ATAK and nothing is logged.

**The fix.** Run the daemon with `--receive-mode=on-connection`, which makes
signal-cli fetch from the servers only while a client is attached; messages then
queue server-side across disconnects. This is now the documented daemon command
everywhere (README, the module docstring, and the runtime hint the bot prints
when the daemon is unreachable).

## 8. A wedged daemon must not freeze the bot silently

**The problem.** The bot's receive loop and its replies run on one thread. The
JSON-RPC calls used `urllib` with no timeout, so a daemon that accepts the TCP
connection but never answers (a GC-paused or deadlocked JVM) would block the
thread forever — no error, no reconnect, the process looking alive while every
subsequent target is ignored.

**The fix.** A 10-second timeout on the request/response calls (`send`, `check`)
and a 120-second read timeout on the long-lived SSE stream (longer than
signal-cli's keep-alive interval, so only a genuinely dead connection trips it).
The handlers catch `OSError` (which covers `socket.timeout`), so a wedged daemon
surfaces as a `SignalRpcError` and the loop reconnects instead of hanging.

## 9. Coordinate order ambiguity

**The problem.** The assignment example `48.567123 39.87897 tank` is labeled
*(longitude, latitude)*, but 48.5° is out of range for a longitude-first reading
of that region — the numbers are actually *(latitude, longitude)*. Silently
trusting the label would place every marker in the wrong hemisphere.

**The fix.** Default to `lat lon` (physical reality), expose `LON_FIRST=true` for
the literal spec order, and *warn* (never silently swap) when the first value
can't be a latitude but the second can — surfacing likely mistakes without
overriding the operator.
