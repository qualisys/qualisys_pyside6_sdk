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

    # Optional: pass a local interface IP as the first argument to bind the
    # discovery socket to a specific NIC. Useful on machines with multiple
    # network interfaces where broadcast on "any" may not reach the QTM subnet.
    # Example:  python discovery_example.py 192.168.10.100
    interface = sys.argv[1] if len(sys.argv) > 1 else None

    print("Searching for QTM instances...")
    if interface:
        print(f"  (binding to interface {interface})")
    print()

    discovery = QTMDiscovery(timeout_ms=2000)
    discovery.discovered.connect(on_discovered)
    discovery.finished.connect(on_finished)
    discovery.start(interface=interface)

    sys.exit(app.exec())
