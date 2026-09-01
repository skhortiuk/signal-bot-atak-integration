"""Signal → Cursor-on-Target (CoT) → ATAK bridge.

Receives Signal messages of the form ``<lat> <lon> <description>``,
converts them into CoT ``<event>`` XML documents and forwards them to a
TAK client (ATAK / iTAK / WinTAK) or a local listener.
"""

__version__ = "0.1.0"
