"""Output sinks: pluggable targets that turn a Target into an emitted event.

A sink implements :class:`~signal_atak.output.base.Sink` and registers in
:mod:`signal_atak.output.factory`. The default sink encodes Cursor-on-Target
and ships it over a transport, but the bot only sees the :class:`Sink`
interface — it does not know the event is CoT.
"""
