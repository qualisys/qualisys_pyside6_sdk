"""PySide6 SDK for QTM Real-Time Protocol"""

import os
import sys

# Add submodule to path for importing packet/receiver
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "qtm_rt"))

from qtm_rt.packet import QRTComponentType, QRTEvent, QRTPacket, QRTPacketType

from .connection import QTMConnection
from .discovery import QTMDiscovery, QTMDiscoveryResponse

__all__ = [
    "QTMConnection",
    "QTMDiscovery",
    "QTMDiscoveryResponse",
    "QRTPacket",
    "QRTEvent",
    "QRTComponentType",
    "QRTPacketType",
]
