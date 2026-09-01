# Cursor-on-Target (CoT) — what this bot emits

Cursor-on-Target is the XML event format ATAK, iTAK and WinTAK speak. Every
marker, track, chat message or sensor reading on a TAK map is a CoT `<event>`.
This bot produces one `<event>` per Signal message and ships it to a TAK client.

All the facts below were checked against the authoritative sources: the MITRE
**CoT Base-Event Schema XSD** and **CoTtypes.xml** catalog (both shipped inside
the official ATAK-CIV repository), plus `pytak`'s implementation.

## The event we build

```xml
<?xml version='1.0' encoding='utf-8'?>
<event version="2.0"
       uid="signal-11112222-3333-4444-5555-666677778888"
       type="a-h-G-E-V-A-T"
       how="m-g"
       time="2026-08-31T12:00:00.500Z"
       start="2026-08-31T12:00:00.500Z"
       stale="2026-08-31T12:10:00.500Z">
  <point lat="48.567123" lon="39.87897" hae="9999999.0" ce="9999999.0" le="9999999.0"/>
  <detail>
    <contact callsign="tank-8888"/>
    <remarks>48.567123 39.87897 tank</remarks>
  </detail>
</event>
```

### `<event>` attributes (all 7 are schema-required)

| Attribute | Meaning | This bot |
|-----------|---------|----------|
| `version` | CoT schema version | `2.0` |
| `uid`     | globally unique event id | `signal-<uuid4>` — a new marker per message |
| `type`    | what the thing is (see below) | from the description |
| `how`     | how the position was derived | `m-g` = machine, from a GPS source |
| `time`    | when the event was generated | now (UTC) |
| `start`   | start of the event's validity | now (UTC) |
| `stale`   | end of validity; the marker fades/drops after this | now + 10 min |

Times are ISO 8601 UTC with a `Z` suffix. The schema allows fractional seconds
but does not require them; we emit milliseconds (`.500Z`), which is valid and
matches what TAK clients expect.

### `<point>` attributes (all 5 required, all decimal)

| Attribute | Meaning | This bot |
|-----------|---------|----------|
| `lat` | latitude, WGS-84 signed degrees, −90..+90 | parsed value |
| `lon` | longitude, WGS-84 signed degrees, −180..+180 | parsed value |
| `hae` | height above the WGS-84 ellipsoid (m) | `9999999.0` = unknown |
| `ce`  | circular error / horizontal accuracy (m) | `9999999.0` = unknown |
| `le`  | linear error / vertical accuracy (m) | `9999999.0` = unknown |

`9999999.0` (seven nines) is the CoT convention for "value not known"; it is
`pytak`'s `DEFAULT_COT_VAL`. A Signal text carries no altitude or accuracy, so
all three take the unknown value.

### `<detail>`

Optional, but it is what makes the marker readable:

- `<contact callsign="…"/>` — the label shown next to the icon. We use
  `<first-word-of-description>-<last 4 of uid>`, e.g. `tank-8888`.
- `<remarks>…</remarks>` — free text (the element body, **not** an attribute).
  We put the original Signal message here so the operator sees exactly what was
  reported.

## CoT type codes

The `type` string is how a TAK client chooses the marker icon. Atom types
(physical things on the map) follow the MIL-STD-2525-derived scheme:

```
a - h - G - E - V - A - T
│   │   │   └────┴───┴──── narrows the thing down: Equipment→Vehicle→Armor→Tank
│   │   └──────────────── battle dimension: G = Ground
│   └──────────────────── affiliation: h hostile, f friendly, n neutral, u unknown
└──────────────────────── a = atom (a real object, vs. b = bits, t = tasking …)
```

The bot maps a description to a type by case-insensitive substring, most
specific first. Every code below is verbatim from MITRE `CoTtypes.xml`:

| Keyword(s) | CoT type | Catalog entry |
|------------|----------|---------------|
| `tank` | `a-h-G-E-V-A-T` | Armor/Tank |
| `apc`, `personnel carrier`, `btr` | `a-h-G-E-V-A-A` | Armor/Apc |
| `bmp`, `ifv` | `a-h-G-E-V-A-I` | Armor/Infantry (IFV) |
| `armor` | `a-h-G-E-V-A` | Armor/Gun (generic) |
| `howitzer` | `a-h-G-E-W-H` | Weapon/Howitzer |
| `artillery` | `a-h-G-U-C-F` | Combat/Artillery |
| `infantry`, `soldier`, `troop` | `a-h-G-U-C-I` | Combat/Infantry/Troops |
| `truck` | `a-h-G-E-V-U` | Vehic/Utility |
| `air defense`, `sam`, `missile` | `a-h-G-E-W-M-A` | Weapon/MissileLauncher/AD |
| `radar` | `a-h-G-E-S-R` | Sensor/Radar |
| `vehicle` | `a-h-G-E-V` | Vehic (generic) |
| *(no match)* | `a-u-G` | Ground track, **unknown** affiliation |

The affiliation letter (`h` by default) is configurable. Note the unmatched
fallback is `a-u-G` — an *unknown* ground track, not a hostile one: if we
couldn't classify the thing, we don't assert it's hostile.

## Two behaviours worth knowing

- **New uid ⇒ new marker.** Reusing a uid *updates* the existing marker in
  ATAK (the XSD says so). We mint a fresh `signal-<uuid4>` each time, so every
  message drops a new pin. A deterministic uid (say, a hash of the location)
  would instead move one marker around — a reasonable alternative for "track
  this thing", but not the default we want for "spotted a target".
- **Stale ⇒ the marker ages out.** At `stale` time ATAK greys the icon and, by
  default, deletes atom (`a-*`) markers a few minutes later. Bump
  `STALE_MINUTES` if you want reports to linger.
