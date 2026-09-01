"""Tests for :mod:`signal_atak.cot_types`."""

from __future__ import annotations

import pytest

from signal_atak.output.cot.types import UNMATCHED_TYPE, cot_type


@pytest.mark.parametrize(
    "description, expected",
    [
        ("tank", "a-h-G-E-V-A-T"),
        ("apc", "a-h-G-E-V-A-A"),
        ("armored personnel carrier", "a-h-G-E-V-A-A"),
        ("infantry", "a-h-G-U-C-I"),
        ("truck", "a-h-G-E-V-U"),
        ("howitzer", "a-h-G-E-W-H"),
        ("artillery", "a-h-G-U-C-F"),
        ("SAM site", "a-h-G-E-W-M-A"),
        ("radar", "a-h-G-E-S-R"),
        ("armor", "a-h-G-E-V-A"),
        ("generic vehicle", "a-h-G-E-V"),
    ],
)
def test_known_keywords(description, expected):
    assert cot_type(description) == expected


def test_case_insensitive():
    assert cot_type("TANK") == "a-h-G-E-V-A-T"


def test_substring_match_in_sentence():
    assert cot_type("2 enemy tanks near treeline") == "a-h-G-E-V-A-T"


def test_unmatched_falls_back_to_unknown_ground():
    assert cot_type("something weird") == UNMATCHED_TYPE
    assert UNMATCHED_TYPE == "a-u-G"


def test_affiliation_applied():
    assert cot_type("tank", affiliation="f") == "a-f-G-E-V-A-T"
    assert cot_type("infantry", affiliation="n") == "a-n-G-U-C-I"


def test_invalid_affiliation_raises():
    with pytest.raises(ValueError, match="affiliation"):
        cot_type("tank", affiliation="z")


def test_first_match_wins_specific_before_generic():
    # "vehicle" also contains no earlier keyword; "tank" is more specific and listed first
    assert cot_type("tank vehicle") == "a-h-G-E-V-A-T"
    assert cot_type("some vehicle") == "a-h-G-E-V"
