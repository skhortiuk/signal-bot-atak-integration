"""Build and parse Cursor-on-Target ``<event>`` XML documents.

A minimal CoT event that every TAK client renders::

    <?xml version='1.0' encoding='utf-8'?>
    <event version="2.0" uid="signal-..." type="a-h-G-E-V-A-T" how="m-g"
           time="..." start="..." stale="...">
      <point lat="48.567123" lon="39.87897" hae="9999999.0"
             ce="9999999.0" le="9999999.0"/>
      <detail>
        <contact callsign="tank-1a2b"/>
        <remarks>48.567123 39.87897 tank</remarks>
      </detail>
    </event>

Design choices (also documented in the README):

* ``uid`` is ``signal-<uuid4>`` — every message creates a *new* marker.
  A deterministic uid (e.g. hash of the description) would instead move
  an existing marker; new-marker semantics fit "spotted a target" better.
* ``hae``/``ce``/``le`` use ``9999999.0``, the CoT convention for
  "unknown", since Signal messages carry no altitude or accuracy.
* ``stale`` defaults to 10 minutes after ``start``; TAK clients fade or
  drop the marker once it goes stale.
* ``how="m-g"`` marks the position as machine-derived GPS-quality data.
"""

from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta

from attrs import frozen

# defusedxml hardens PARSING against XXE / billion-laughs. Building XML with
# the stdlib ElementTree is not a parse and is unaffected; only parse_cot,
# which reads bytes off the network, needs the hardened parser.
from defusedxml.ElementTree import fromstring as safe_fromstring

from ...parser import Target
from .types import cot_type

#: CoT convention for "value not known"
UNKNOWN = "9999999.0"


@frozen
class CotEvent:
    """A CoT event decoded from XML — the listener's typed view of a marker.

    A *delete* event (``type`` ``t-x-d-d``) is a retraction: ``is_delete``
    is ``True`` and ``link_uid`` names the marker to remove, rather than a
    new marker to add.
    """

    uid: str
    type: str
    lat: float
    lon: float
    callsign: str = ""
    remarks: str = ""
    stale: str = ""
    is_delete: bool = False
    link_uid: str = ""


#: CoT type of a "delete" task — tells a TAK client to remove a map item.
DELETE_TYPE = "t-x-d-d"


class CotParseError(ValueError):
    """Raised when bytes off the wire are not a usable CoT event."""


def _cot_time(moment: datetime) -> str:
    """Format a datetime as CoT expects: ISO 8601 UTC, millisecond precision, ``Z``.

    The value is converted to UTC first, so a caller passing a
    timezone-aware non-UTC datetime still gets a correct ``Z`` timestamp
    rather than local wall-clock digits mislabelled as UTC.
    """
    moment = moment.astimezone(UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def _fmt_coord(value: float) -> str:
    """Format a coordinate as a plain decimal (never scientific notation).

    ``f"{1e-05}"`` yields ``'1e-05'``, which violates CoT's ``xs:decimal``
    and can be misparsed by TAK clients. Fixed-point formatting with
    trailing zeros stripped keeps full precision for real coordinates and
    stays plain-decimal for values near zero.
    """
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    return text or "0"


def build_cot(
    target: Target,
    *,
    affiliation: str = "h",
    stale_minutes: float = 10.0,
    now: datetime | None = None,
    uid: str | None = None,
) -> bytes:
    """Serialise ``target`` into a CoT ``<event>`` XML document.

    :param affiliation: CoT affiliation letter for the type code (default hostile).
    :param stale_minutes: marker lifetime; after this the TAK client
        considers the report outdated.
    :param now: event time override for deterministic tests (must be
        timezone-aware); defaults to the current UTC time.
    :param uid: uid override for deterministic tests; defaults to
        ``signal-<uuid4>``.
    :returns: UTF-8 encoded XML with declaration, ready to send.
    """
    if now is None:
        now = datetime.now(UTC)
    if uid is None:
        uid = f"signal-{uuid.uuid4()}"

    event = ET.Element(
        "event",
        version="2.0",
        uid=uid,
        type=cot_type(target.description, affiliation=affiliation),
        how="m-g",
        time=_cot_time(now),
        start=_cot_time(now),
        stale=_cot_time(now + timedelta(minutes=stale_minutes)),
    )
    ET.SubElement(
        event,
        "point",
        lat=_fmt_coord(target.lat),
        lon=_fmt_coord(target.lon),
        hae=UNKNOWN,
        ce=UNKNOWN,
        le=UNKNOWN,
    )
    detail = ET.SubElement(event, "detail")
    ET.SubElement(detail, "contact", callsign=_callsign(target.description, uid))
    remarks = ET.SubElement(detail, "remarks")
    remarks.text = f"{target.lat} {target.lon} {target.description}"

    return ET.tostring(event, encoding="utf-8", xml_declaration=True)


def _callsign(description: str, uid: str) -> str:
    """Short human-readable marker label: first word of the description + uid tail."""
    word = description.split()[0][:16]
    return f"{word}-{uid[-4:]}"


def build_delete_cot(
    target_uid: str,
    *,
    now: datetime | None = None,
    uid: str | None = None,
) -> bytes:
    """Build a CoT *delete* event that retracts the marker ``target_uid``.

    This is the standard TAK mechanism for removing a map item: a
    ``t-x-d-d`` task event whose ``<detail><link>`` names the target uid.
    TAK clients (ATAK/iTAK/WinTAK) delete the referenced marker on receipt;
    the bundled listener honours it too.

    :param target_uid: uid of the marker to remove.
    :param now: time override for deterministic tests.
    :param uid: this event's own uid override for tests.
    """
    if now is None:
        now = datetime.now(UTC)
    if uid is None:
        uid = f"signal-del-{uuid.uuid4()}"

    event = ET.Element(
        "event",
        version="2.0",
        uid=uid,
        type=DELETE_TYPE,
        how="m-g",
        time=_cot_time(now),
        start=_cot_time(now),
        stale=_cot_time(now + timedelta(minutes=1)),
    )
    # a point is schema-required even for a delete; 0/0 with unknown accuracy
    ET.SubElement(event, "point", lat="0", lon="0", hae=UNKNOWN, ce=UNKNOWN, le=UNKNOWN)
    detail = ET.SubElement(event, "detail")
    ET.SubElement(detail, "link", uid=target_uid, relation="none", type="none")
    ET.SubElement(detail, "__forcedelete")
    return ET.tostring(event, encoding="utf-8", xml_declaration=True)


def parse_cot(cot_xml: bytes | str) -> CotEvent:
    """Decode a CoT ``<event>`` document into a :class:`CotEvent`.

    Uses a hardened XML parser because the input arrives over the network.

    :raises CotParseError: on malformed XML or a missing ``<point>``.
    """
    try:
        event = safe_fromstring(cot_xml)
    except Exception as exc:  # defusedxml raises several stdlib/ET types
        raise CotParseError(f"Not well-formed CoT XML: {exc}") from exc

    if event.tag != "event":
        raise CotParseError(f"Root element is <{event.tag}>, expected <event>")

    cot_type_str = event.attrib.get("type", "")
    is_delete = cot_type_str.startswith(DELETE_TYPE)

    point = event.find("point")
    if point is None:
        raise CotParseError("CoT event has no <point>")
    try:
        lat = float(point.attrib["lat"])
        lon = float(point.attrib["lon"])
    except (KeyError, ValueError) as exc:
        raise CotParseError(f"CoT <point> missing usable lat/lon: {exc}") from exc

    link = event.find("./detail/link")
    contact = event.find("./detail/contact")
    remarks = event.find("./detail/remarks")
    return CotEvent(
        uid=event.attrib.get("uid", ""),
        type=cot_type_str,
        lat=lat,
        lon=lon,
        callsign=contact.attrib.get("callsign", "") if contact is not None else "",
        remarks=(remarks.text or "") if remarks is not None else "",
        stale=event.attrib.get("stale", ""),
        is_delete=is_delete,
        link_uid=link.attrib.get("uid", "") if link is not None else "",
    )
