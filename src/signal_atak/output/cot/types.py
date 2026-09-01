"""Map free-text target descriptions to CoT type codes.

CoT "atom" types follow the pattern ``a-<affiliation>-<dimension>-...``
derived from MIL-STD-2525: ``a`` = atom (a physical thing on the map),
the second token is the affiliation (``h`` hostile, ``f`` friendly,
``n`` neutral, ``u`` unknown), ``G`` = ground dimension, and the tail
narrows the thing down (``E-V-A-T`` = equipment / vehicle / armored /
tank). TAK clients pick the marker icon from this string.
"""

from __future__ import annotations

#: keyword → type template; ``{a}`` is replaced with the affiliation.
#: First match wins, so more specific keywords precede generic ones
#: (``tank`` before ``armor``, ``apc`` before ``vehicle``). All codes are
#: taken verbatim from MITRE ``CoTtypes.xml`` (the catalog ATAK ships);
#: the ``full`` path from that file is quoted for provenance.
_KEYWORD_TYPES: tuple[tuple[str, str], ...] = (
    ("tank", "a-{a}-G-E-V-A-T"),  # Gnd/Equip/Vehic/Armor/Tank
    ("apc", "a-{a}-G-E-V-A-A"),  # Gnd/Equip/Vehic/Armor/Apc
    ("personnel carrier", "a-{a}-G-E-V-A-A"),
    ("btr", "a-{a}-G-E-V-A-A"),
    ("bmp", "a-{a}-G-E-V-A-I"),  # Gnd/Equip/Vehic/Armor/Infantry (IFV)
    ("ifv", "a-{a}-G-E-V-A-I"),
    ("howitzer", "a-{a}-G-E-W-H"),  # Gnd/Equip/Weapon/Howitzer
    ("artillery", "a-{a}-G-U-C-F"),  # Gnd/Combat/Artillery (Fixed)
    ("infantry", "a-{a}-G-U-C-I"),  # Gnd/Combat/Infantry/Troops
    ("soldier", "a-{a}-G-U-C-I"),
    ("troop", "a-{a}-G-U-C-I"),
    ("truck", "a-{a}-G-E-V-U"),  # Gnd/Equip/Vehic/Utility
    ("air defense", "a-{a}-G-E-W-M-A"),  # Gnd/Equip/Weapon/MissileLauncher/Ad
    ("sam", "a-{a}-G-E-W-M-A"),
    ("missile", "a-{a}-G-E-W-M-A"),
    ("radar", "a-{a}-G-E-S-R"),  # Gnd/Equip/Sensor/Radar
    ("armor", "a-{a}-G-E-V-A"),  # Gnd/Equip/Vehic/Armor/Gun (generic armor)
    ("vehicle", "a-{a}-G-E-V"),  # Gnd/Equip/Vehic (generic vehicle)
)

#: fallback when no keyword matches: an *unknown* ground track — the
#: affiliation is deliberately NOT applied because we could not classify
#: the thing, so claiming it hostile would overstate what we know.
UNMATCHED_TYPE = "a-u-G"

VALID_AFFILIATIONS = frozenset("fhnsu")  # friendly, hostile, neutral, suspect, unknown


def cot_type(description: str, *, affiliation: str = "h") -> str:
    """Return the CoT type code for a free-text ``description``.

    Matching is case-insensitive on substrings, so ``"2 enemy tanks"``
    maps the same as ``"tank"``. Unmatched descriptions fall back to
    :data:`UNMATCHED_TYPE`.

    :param affiliation: single-letter CoT affiliation, default hostile
        (the bot's domain is *targets*).
    :raises ValueError: on an affiliation letter CoT does not define.
    """
    if affiliation not in VALID_AFFILIATIONS:
        raise ValueError(
            f"Invalid affiliation {affiliation!r}; expected one of {sorted(VALID_AFFILIATIONS)}"
        )

    lowered = description.lower()
    for keyword, template in _KEYWORD_TYPES:
        if keyword in lowered:
            return template.format(a=affiliation)
    return UNMATCHED_TYPE
