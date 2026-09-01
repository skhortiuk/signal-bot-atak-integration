"""Tests for :mod:`signal_atak.config`."""

from __future__ import annotations

import pytest

from signal_atak.config import Config, load_config


def test_load_from_env_file(tmp_path, monkeypatch):
    for var in ("SIGNAL_ACCOUNT", "COT_URL", "LON_FIRST", "ALLOWED_SENDERS"):
        monkeypatch.delenv(var, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "SIGNAL_ACCOUNT=+380501234567\n"
        "COT_URL=tcp://127.0.0.1:4242\n"
        "LON_FIRST=true\n"
        "# a comment\n"
        "ALLOWED_SENDERS=+380501234567, +15551230000\n"
    )
    cfg = load_config(env)
    assert cfg.signal_account == "+380501234567"
    assert cfg.cot_url == "tcp://127.0.0.1:4242"
    assert cfg.lon_first is True
    assert cfg.allowed_senders == ("+380501234567", "+15551230000")


def test_environment_overrides_file(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("SIGNAL_ACCOUNT=+1\nCOT_URL=log://stdout\n")
    monkeypatch.setenv("COT_URL", "udp://239.2.3.1:6969")
    cfg = load_config(env)
    assert cfg.cot_url == "udp://239.2.3.1:6969"


def test_missing_account_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("SIGNAL_ACCOUNT", raising=False)
    with pytest.raises(KeyError, match="SIGNAL_ACCOUNT"):
        load_config(tmp_path / "nonexistent.env")


def test_sender_allowed_defaults_to_own_account():
    cfg = Config(signal_account="+1", allowed_senders=())
    assert cfg.sender_allowed("+1") is True
    assert cfg.sender_allowed("+2") is False


def test_sender_allowed_wildcard():
    cfg = Config(signal_account="+1", allowed_senders=("*",))
    assert cfg.sender_allowed("+anyone") is True


def test_invalid_affiliation_rejected():
    with pytest.raises(ValueError):
        Config(signal_account="+1", affiliation="z")
