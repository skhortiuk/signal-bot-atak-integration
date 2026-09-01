"""Messaging platforms: pluggable chat backends behind a common interface.

A platform (Signal, Telegram, …) implements :class:`~signal_atak.messaging.base.Messenger`
and registers itself in :mod:`signal_atak.messaging.factory`. ``bot.py`` never
imports a concrete platform — it depends only on the protocol.
"""
