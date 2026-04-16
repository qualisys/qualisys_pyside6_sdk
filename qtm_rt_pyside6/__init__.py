"""PySide6 SDK for QTM Real-Time Protocol"""

import logging

from qtm_rt.packet import QRTComponentType, QRTEvent, QRTPacket, QRTPacketType

from .connection import QTMConnection
from .discovery import QTMDiscovery, QTMDiscoveryResponse

# Library logger hygiene: avoid "No handlers could be found" warnings when the
# host application has not configured logging. Users can attach their own
# handlers to the "qtm_rt_pyside6" logger if they want output.
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "QTMConnection",
    "QTMDiscovery",
    "QTMDiscoveryResponse",
    "QRTPacket",
    "QRTEvent",
    "QRTComponentType",
    "QRTPacketType",
]
