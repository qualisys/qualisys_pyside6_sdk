"""
Basic example - Stream 3D markers from QTM

Start QTM first, load a file, and enable Play -> Play with Real-Time output
"""

import sys
from PySide6.QtCore import QCoreApplication
from qtm_rt_pyside6 import QTMConnection, QRTPacket


class StreamingApp:
    def __init__(self):
        self.connection = QTMConnection()

        # Connect signals
        self.connection.connected.connect(self.on_connected)
        self.connection.disconnected.connect(self.on_disconnected)
        self.connection.error.connect(self.on_error)
        self.connection.packetReceived.connect(self.on_packet)

    def start(self, host: str = "127.0.0.1"):
        print(f"Connecting to {host}...")
        self.connection.connectToHost(host)

    def on_connected(self):
        print("Connected! Starting 3D stream...")
        self.connection.streamFrames(components=["3d"])

    def on_disconnected(self):
        print("Disconnected")
        QCoreApplication.quit()

    def on_error(self, error: str):
        print(f"Error: {error}")
        QCoreApplication.quit()

    def on_packet(self, packet: QRTPacket):
        print(f"Frame {packet.framenumber}")

        result = packet.get_3d_markers()
        if result is not None:
            header, markers = result
            print(f"  {header.marker_count} markers")
            for i, marker in enumerate(markers[:5]):  # Show first 5
                print(f"    [{i}] x={marker.x:.1f} y={marker.y:.1f} z={marker.z:.1f}")
            if header.marker_count > 5:
                print(f"    ... and {header.marker_count - 5} more")


if __name__ == "__main__":
    app = QCoreApplication(sys.argv)

    streaming = StreamingApp()
    streaming.start()

    sys.exit(app.exec())
