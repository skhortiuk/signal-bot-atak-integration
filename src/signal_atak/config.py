"""Bot configuration: a frozen attrs object loaded from the environment.

Precedence: process environment > ``.env`` file > defaults. The ``.env``
loader is deliberately tiny (KEY=VALUE lines, ``#`` comments) to avoid a
dependency for twelve lines of behaviour.
"""

from __future__ import annotations

import os
from pathlib import Path

from attrs import field, frozen, validators

from .output.cot.types import VALID_AFFILIATIONS

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _to_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return value.strip().lower() in _TRUTHY


def _to_senders(value: str | tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(value, tuple):
        return value
    return tuple(s.strip() for s in value.split(",") if s.strip())


@frozen
class Config:
    """Everything the bot needs to run; immutable once loaded."""

    signal_account: str = field(validator=validators.min_len(1))
    signal_http: str = "127.0.0.1:8080"
    cot_url: str = "udp://239.2.3.1:6969"
    #: which chat backend to run (see signal_atak.messaging.factory)
    messaging_platform: str = "signal"
    #: which output format to emit (see signal_atak.output.factory)
    output_sink: str = "cot"
    #: senders the bot reacts to; empty means "only the bot's own account"
    #: (the Note-to-Self setup). ``("*",)`` accepts anyone.
    allowed_senders: tuple[str, ...] = field(default=(), converter=_to_senders)
    lon_first: bool = field(default=False, converter=_to_bool)
    stale_minutes: float = field(default=10.0, converter=float)
    affiliation: str = field(default="h", validator=validators.in_(VALID_AFFILIATIONS))
    log_level: str = "INFO"

    def sender_allowed(self, number: str | None) -> bool:
        """Is ``number`` allowed to command the bot?"""
        if "*" in self.allowed_senders:
            return True
        allowed = self.allowed_senders or (self.signal_account,)
        return number in allowed


def _read_env_file(path: Path) -> dict[str, str]:
    """Parse a minimal KEY=VALUE ``.env`` file; missing file → empty dict."""
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def load_config(env_file: Path | None = None) -> Config:
    """Build a :class:`Config` from ``os.environ`` overlaid on ``env_file``.

    :raises KeyError: when ``SIGNAL_ACCOUNT`` is missing — the one value
        that has no sane default.
    """
    file_values = _read_env_file(env_file if env_file is not None else Path(".env"))

    def get(name: str, default: str | None = None) -> str | None:
        return os.environ.get(name, file_values.get(name, default))

    account = get("SIGNAL_ACCOUNT")
    if not account:
        raise KeyError(
            "SIGNAL_ACCOUNT is not set (E.164 number of the Signal account, e.g. +380501234567)"
        )

    return Config(
        signal_account=account,
        signal_http=get("SIGNAL_HTTP", "127.0.0.1:8080"),
        cot_url=get("COT_URL", "udp://239.2.3.1:6969"),
        messaging_platform=get("MESSAGING_PLATFORM", "signal"),
        output_sink=get("OUTPUT_SINK", "cot"),
        allowed_senders=get("ALLOWED_SENDERS", ""),
        lon_first=get("LON_FIRST", "false"),
        stale_minutes=get("STALE_MINUTES", "10"),
        affiliation=get("AFFILIATION", "h"),
        log_level=get("LOG_LEVEL", "INFO"),
    )
