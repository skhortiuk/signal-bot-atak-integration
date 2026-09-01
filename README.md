# signal-atak — a Signal bot that drops targets onto ATAK

Send a Signal message like `48.567123 39.87897 tank` and a marker appears on an
ATAK / iTAK / WinTAK map. The bot parses the coordinates and description, builds
a **Cursor-on-Target (CoT)** event, ships it to a TAK client, and replies in
Signal with a confirmation.

```
 Signal app ──▶ signal-cli daemon ──▶ signal_atak.bot ──▶ TAK sender ──▶ ATAK / iTAK / WinTAK
 (your phone)     (HTTP JSON-RPC)      parse → CoT XML      udp/tcp/log      (or the local
                                            │                                  cot_listener)
                                            └──▶ reply "✅ sent to ATAK…"
```

## Approach

The pipeline is four small, independently testable steps:

1. **Parse** `text → Target(lat, lon, description)` with range validation and
   swapped-order detection (`parser.py`).
2. **Classify** the description into a CoT type code (`cot_types.py`), using the
   MITRE type catalog that ships with ATAK.
3. **Build** a spec-compliant CoT `<event>` XML document (`cot.py`).
4. **Deliver** it to a `COT_URL` — multicast, TCP, UDP, or stdout
   (`tak_sender.py`) — and **reply** in Signal (`signal_client.py`, `bot.py`).

The two genuinely tricky parts are isolated as pure functions with heavy tests:
the Signal receive-path normaliser (the Note-to-Self quirk, below) and the CoT
builder. Everything that touches the network sits behind an interface so the
logic is tested without a phone, a TAK client, or a running daemon.

**The bot is platform- and output-agnostic.** It depends only on two protocols:
a `Messenger` (a chat backend) and a `Sink` (a target destination). Signal and
CoT are just the implementations that ship — each lives behind a small registry,
so adding a chat platform (Telegram, …) or an output format is one new module
plus one registry entry, with no change to `bot.py`.

Tools used: Python 3.11+, `attrs`/`cattrs` (typed immutable models),
`defusedxml` (safe XML parsing), `folium` (the test map), `pytest`/`ruff`/
`black`, and `signal-cli` (external, via Homebrew) as the Signal bridge.
The design decision to use stdlib sockets instead of `pytak` is explained in
[`docs/challenges.md`](docs/challenges.md).

## Repository layout

```
src/signal_atak/
  parser.py            text → Target, with validation + swap detection
  config.py            env / .env configuration + platform/output selectors
  bot.py               main loop: receive → parse → sink.emit → reply
                       (depends ONLY on the Messenger + Sink protocols)
  __main__.py          python -m signal_atak (wires it up via the registries)
  messaging/           chat backends behind a common interface
    base.py            Messenger protocol + InboundMessage (platform-neutral)
    signal.py          signal-cli HTTP/JSON-RPC + SSE, incl. sync transcripts
    factory.py         name → Messenger registry (build_messenger)
  output/              target destinations behind a common interface
    base.py            Sink protocol: emit(Target)
    transport.py       byte transports for a COT_URL (udp/tcp/log)
    cot_sink.py        CotSink = CoT-encode + transport
    factory.py         name → Sink registry (build_sink)
    cot/
      types.py         description → CoT type code (MITRE catalog)
      encode.py        Target → CoT XML; also parse_cot for the listener
tools/cot_listener.py  local CoT listener + folium map (a fake TAK client)
tests/                 pytest suite (parser, cot, types, config, transport,
                       cot_sink, signal, bot)
docs/                  cot_protocol.md, challenges.md
```

### Adding a platform or output

- **New chat platform:** add `messaging/<name>.py` with a class implementing
  `Messenger` (its `receive()` yields `InboundMessage`, `send()` posts a reply),
  then register it in `messaging/factory.py`. Select with `MESSAGING_PLATFORM`.
- **New output format:** add a `Sink` (or reuse `CotSink` with a new transport),
  register it in `output/factory.py`, select with `OUTPUT_SINK`.

## Setup

### 1. Python environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt        # runtime deps
pip install -e ".[dev]"                # + pytest/ruff/black for development
```

Run the tests — this passes with **no** phone, daemon, or TAK client:

```bash
pytest            # 89 tests, all offline
```

### 2. Link signal-cli to your Signal account

The bot uses your **existing** account as a **linked device** (no new number, no
captcha). Install a current signal-cli — 0.14.x or newer; older builds stop
working against Signal's servers:

```bash
brew install signal-cli
signal-cli link -n "atak-bot"
```

`link` prints a QR code in the terminal (0.14.0+). On your phone:
**Signal → Settings → Linked Devices → +** and scan it. Wait for the command to
finish; it prints your account number when linking completes.

### 3. Start the signal-cli daemon

```bash
signal-cli -a +YOURNUMBER daemon --http=127.0.0.1:8080 --receive-mode=on-connection
```

This exposes the JSON-RPC HTTP API the bot talks to (`POST /api/v1/rpc` to send,
`GET /api/v1/events` SSE stream to receive). Leave it running.

`--receive-mode=on-connection` is important: without it, signal-cli's default
(`on-start`) pulls and acknowledges messages from Signal's servers even when no
client is listening — so anything that arrives while the bot is reconnecting or
down is acked to nobody and lost. `on-connection` makes the daemon fetch only
while the bot's SSE stream is attached, so messages queue server-side across
disconnects. See [`docs/challenges.md`](docs/challenges.md).

### 4. Configure and run the bot

```bash
cp .env.example .env      # then edit SIGNAL_ACCOUNT and COT_URL
python -m signal_atak
```

## Run & demo

You can demo the whole chain **without a TAK device** using the bundled listener.

**Terminal A — the fake TAK client:**
```bash
python tools/cot_listener.py --tcp 127.0.0.1:4242
# open cot_map.html in a browser; it refreshes as markers arrive
```

**Terminal B — the bot, pointed at the listener:**
```bash
COT_URL=tcp://127.0.0.1:4242 python -m signal_atak
```

Now send yourself `48.567123 39.87897 tank` in Signal (Note-to-Self). You should
see the listener log the CoT, a pin appear in `cot_map.html`, and a `✅` reply
in the chat.

Prefer to eyeball the raw protocol? `COT_URL=log://stdout python -m signal_atak`
prints the CoT XML for each message.

### Delivering to a real iTAK / WinTAK

Two routes, both documented so you can pick what your network allows:

- **Multicast (try first):** `COT_URL=udp://239.2.3.1:6969`. This is the ATAK/iTAK
  default SA mesh group; on the same Wi-Fi it often works with no client config.
  Some routers drop multicast (IGMP snooping, AP client isolation) — if the
  marker never shows, use the TCP route.
- **TCP unicast (reliable):** add a network input in iTAK
  (**Settings → Network → Inputs/Outputs**) or WinTAK for TCP on a port, then set
  `COT_URL=tcp://<device_ip>:<port>`. This crosses routers that block multicast.

## Key decisions & assumptions

- **Coordinate order is `lat lon` by default.** The assignment example labels
  `48.567123 39.87897` as *(longitude, latitude)*, but 48.5° can only be a
  latitude and 39.9° a longitude for the region described — the label is a typo.
  Set `LON_FIRST=true` to honour the literal spec order. Out-of-range-looking
  input is warned about, never silently reordered.
- **Note-to-Self testing** means the bot reads its own sent messages via Signal
  **sync transcripts** (`syncMessage.sentMessage`), not ordinary incoming
  messages — see [`docs/challenges.md`](docs/challenges.md). This is the central
  quirk of the design.
- **Affiliation defaults to hostile (`h`)** — the domain is targets. Configurable.
- **hae/ce/le = `9999999.0`** (CoT "unknown"), since a text has no altitude/accuracy.
- **stale = 10 minutes**, **uid = `signal-<uuid4>`** (a fresh marker per message).
- **signal-cli is a linked device** of your existing account, not a new number.

## Limitations

- One target per message; no attachments, groups, or media.
- signal-cli must be linked and its daemon running — the bot does not manage it.
- Multicast delivery depends on the local network; TCP is the reliable fallback.
- iTAK/WinTAK accept legacy XML CoT on a plain input; a full TAK Server
  (protobuf/TLS) is out of scope.

## Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| Bot silent to your messages | You're on Note-to-Self and messages arrive as sync transcripts — this bot handles that; check the daemon is up (`GET /api/v1/check`) and `SIGNAL_ACCOUNT` matches. |
| `signal-cli daemon not reachable` | Start `signal-cli -a … daemon --http=127.0.0.1:8080 --receive-mode=on-connection` and check the port matches `SIGNAL_HTTP`. |
| Messages lost after a bot restart/reconnect | The daemon was started without `--receive-mode=on-connection` — see step 3 and `docs/challenges.md`. |
| Marker never appears in iTAK | Multicast dropped by the router — switch to `COT_URL=tcp://<device_ip>:<port>` and add the input in iTAK. |
| `link` seems to hang | It waits until you scan the QR; don't kill it before then. |
| Nothing on the map | Confirm the listener printed the CoT line; open/refresh `cot_map.html`. |
