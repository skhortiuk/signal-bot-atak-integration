"""Parse Signal message text into a validated :class:`Target`.

Accepted shape: two decimal numbers followed by a free-text description,
separated by whitespace and/or commas, e.g.::

    48.567123 39.87897 tank
    48.567123, 39.87897, enemy APC near bridge

Coordinate order
----------------
The first number is treated as **latitude** by default. The assignment
example labels ``48.567123 39.87897`` as (longitude, latitude), but 48.5°
can only be a latitude for the region the example describes, so the label
is taken to be a typo. Set ``lon_first=True`` to honour the literal
spec order instead.

Contract
--------
* Text that does not look like a target message at all → ``None``
  (the bot must stay silent on ordinary chatter — this is also the
  guard that stops it reacting to its own replies).
* Text that matches the shape but carries invalid coordinates →
  :class:`InvalidCoordinateError` (the bot replies with the message).
"""

from __future__ import annotations

import logging
import re

from attrs import field, frozen, validators

logger = logging.getLogger(__name__)

#: two signed decimals, then a non-empty description; commas allowed as separators
_TARGET_RE = re.compile(
    r"^\s*(-?\d{1,3}(?:\.\d+)?)\s*[,\s]\s*(-?\d{1,3}(?:\.\d+)?)\s*[,\s]\s*(\S.*?)\s*$"
)


class InvalidCoordinateError(ValueError):
    """Coordinate-shaped message with out-of-range or unusable values.

    ``str(error)`` is written for humans and is sent back to the Signal
    sender verbatim.
    """


@frozen
class Target:
    """A validated geolocated target ready for CoT conversion.

    The attrs validators make invalid instances unrepresentable — even
    code that bypasses :func:`parse_target` cannot build an out-of-range
    target. The parser exists on top of this to turn violations into
    human-readable Signal replies.
    """

    lat: float = field(validator=[validators.ge(-90.0), validators.le(90.0)])
    lon: float = field(validator=[validators.ge(-180.0), validators.le(180.0)])
    description: str = field(validator=validators.min_len(1))


def parse_target(text: str, *, lon_first: bool = False) -> Target | None:
    """Parse ``text`` into a :class:`Target`.

    :param text: raw Signal message body.
    :param lon_first: interpret the first number as longitude
        (the assignment's literal order) instead of latitude.
    :returns: the parsed target, or ``None`` when ``text`` is not a
        target message (no reply should be sent in that case).
    :raises InvalidCoordinateError: when the message matches the target
        shape but the coordinates are out of range.
    """
    match = _TARGET_RE.match(text or "")
    if match is None:
        return None

    first, second = float(match.group(1)), float(match.group(2))
    description = match.group(3)

    lat, lon = (second, first) if lon_first else (first, second)

    if not lon_first and abs(first) > 90.0 and abs(second) <= 90.0:
        logger.warning(
            "Coordinate order looks swapped (first value %s cannot be a latitude, "
            "second value %s could be). If you meant 'lon lat', set LON_FIRST=true.",
            first,
            second,
        )

    if not -90.0 <= lat <= 90.0:
        raise InvalidCoordinateError(
            f"Latitude {lat} is out of range [-90, 90]. "
            f"Expected '<lat> <lon> <description>'"
            + (" with LON_FIRST=true active" if lon_first else "")
            + "."
        )
    if not -180.0 <= lon <= 180.0:
        raise InvalidCoordinateError(f"Longitude {lon} is out of range [-180, 180].")

    return Target(lat=lat, lon=lon, description=description)
