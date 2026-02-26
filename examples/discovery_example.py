"""
Discovery example - Find QTM instances on the network
"""

import sys
from PySide6.QtCore import QCoreApplication
from qtm_rt_pyside6 import QTMDiscovery, QTMDiscoveryResponse


def on_discovered(response: QTMDiscoveryResponse):
    print(f"Found QTM: {response.info}")
    print(f"  Host: {response.host}")
    print(f"  Port: {response.port}")
    print()


def on_finished():
    print("Discovery finished")
    QCoreApplication.quit()


if __name__ == "__main__":
    app = QCoreApplication(sys.argv)

    print("Searching for QTM instances...")
    print()

    discovery = QTMDiscovery(timeout_ms=2000)
    discovery.discovered.connect(on_discovered)
    discovery.finished.connect(on_finished)
    discovery.start()

    sys.exit(app.exec())
