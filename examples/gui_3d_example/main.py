"""
Qt Quick 3D example - QTM markers, bones, rigid bodies and skeletons in 3D

Built on the SDK's scene helpers (pip install "qtm-rt-pyside6[scene]"): a
QtmScene follows the connection and main.qml draws it with QtmView, next to a
panel that lists what QTM has defined. Click a name in the panel, or a point in
the 3D view, to highlight it. No QTM at hand? Switch on "Demo data" (or start
with --demo).

Mouse as in QTM: left-drag orbits, right-drag pans, the wheel zooms.

Optional: drop Montserrat / Open Sans .ttf files into a `fonts` folder next to
this script; otherwise the system font is used.
"""

import sys
from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from qtm_rt_pyside6 import QTMConnection, QTMDiscovery
from qtm_rt_pyside6.scene import DemoSource, QtmScene, apply_theme, load_fonts
from qtm_rt_pyside6.scene.quick3d import setup_engine

HERE = Path(__file__).resolve().parent


def scene_tree(labels: list[str], skeletons: list[str], bodies: list[str]) -> list[dict]:
    """Rows for the side panel: headers, marker groups (by the prefix before the last "_") and items.

    Each row has the names it highlights when clicked."""
    groups: dict[str, list[str]] = {}
    ungrouped = []
    for name in labels:
        if "_" in name:
            groups.setdefault(name.rsplit("_", 1)[0], []).append(name)
        else:
            ungrouped.append(name)

    rows = [{"text": f"Markers ({len(labels)})", "kind": "header", "indent": 0, "names": []}]
    for prefix in sorted(groups):
        names = groups[prefix]
        rows.append({"text": f"{prefix} ({len(names)})", "kind": "group", "indent": 1, "names": names})
        rows += [{"text": n.rsplit("_", 1)[1], "kind": "marker", "indent": 2, "names": [n]} for n in names]
    rows += [{"text": n, "kind": "marker", "indent": 1, "names": [n]} for n in ungrouped]
    rows.append({"text": f"Skeletons ({len(skeletons)})", "kind": "header", "indent": 0, "names": []})
    rows += [{"text": n, "kind": "skeleton", "indent": 1, "names": [n]} for n in skeletons]
    rows.append({"text": f"Rigid bodies ({len(bodies)})", "kind": "header", "indent": 0, "names": []})
    rows += [{"text": n, "kind": "body", "indent": 1, "names": [n]} for n in bodies]
    return rows


class Backend(QObject):
    """Connection, discovery and demo data for main.qml; the QtmScene does the rest."""

    connectedChanged = Signal()
    statusChanged = Signal()
    hostsChanged = Signal()
    discoveringChanged = Signal()
    demoChanged = Signal()
    treeChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._status = "Not connected. Connect to QTM, or switch on Demo data."
        self._hosts = ["127.0.0.1"]
        self._discovering = False
        self._tree = scene_tree([], [], [])

        self._connection = QTMConnection(self)
        self._connection.connected.connect(self._on_connected)
        self._connection.disconnected.connect(self._on_disconnected)
        self._connection.error.connect(lambda message: self._set_status(f"QTM: {message}"))

        self._scene = QtmScene(self._connection, self)
        self._scene.parametersChanged.connect(self._on_parameters)
        self._demo = DemoSource(self._scene, self)
        self._demo.runningChanged.connect(self.demoChanged)

        self._discovery = QTMDiscovery(self, timeout_ms=1500)
        self._discovery.discovered.connect(self._on_discovered)
        self._discovery.finished.connect(self._on_discovery_finished)

    @Property(QObject, constant=True)
    def scene(self):
        return self._scene

    @Property(bool, notify=connectedChanged)
    def connected(self):
        return self._connection.isConnected()

    @Property(str, notify=statusChanged)
    def status(self):
        return self._status

    @Property(list, notify=hostsChanged)
    def hosts(self):
        return self._hosts

    @Property(bool, notify=discoveringChanged)
    def discovering(self):
        return self._discovering

    @Property(list, notify=treeChanged)
    def tree(self):
        return self._tree

    def _get_demo(self):
        return self._demo.running

    def _set_demo(self, on: bool):
        if on and not self._connection.isConnected():
            self._demo.start()
            self._set_status("Demo data: a simulated skeleton walking on the spot, with markers and a rigid body")
        elif not on and self._demo.running:
            self._demo.stop()
            self._set_status("Not connected. Connect to QTM, or switch on Demo data.")

    demo = Property(bool, _get_demo, _set_demo, notify=demoChanged)

    @Slot(str)
    def connectTo(self, host: str):
        self._set_demo(False)
        host = host.strip() or "127.0.0.1"
        self._set_status(f"Connecting to {host}...")
        self._connection.connectToHost(host)

    @Slot()
    def disconnectFromQtm(self):
        self._connection.disconnectFromHost()

    @Slot()
    def discover(self):
        self._discovering = True
        self.discoveringChanged.emit()
        self._set_status("Looking for QTM on the network...")
        self._discovery.start()

    def _on_connected(self):
        self.connectedChanged.emit()
        self._set_status("Connected; streaming as soon as QTM has sent its parameters")

    def _on_disconnected(self):
        self.connectedChanged.emit()
        self._set_status("Disconnected")

    def _on_parameters(self):
        s = self._scene
        self._tree = scene_tree(s.labels, s.skeletonNames, s.bodyNames)
        self.treeChanged.emit()

    def _on_discovered(self, response):
        if response.host not in self._hosts:
            self._hosts = self._hosts + [response.host]
            self.hostsChanged.emit()

    def _on_discovery_finished(self):
        self._discovering = False
        self.discoveringChanged.emit()
        found = len(self._hosts) - 1
        self._set_status(f"Found {found} QTM instance(s)" if found else "No QTM found on the network")

    def _set_status(self, text: str):
        if text != self._status:
            self._status = text
            self.statusChanged.emit()

    def shutdown(self):
        self._demo.stop()
        if self._connection.isConnected():
            self._connection.disconnectFromHost()


def main():
    app = QGuiApplication(sys.argv)
    app.setApplicationName("QTM 3D Viewer")
    apply_theme(app)  # before the QML engine: the controls' style is picked once
    load_fonts(HERE / "fonts")

    backend = Backend()
    app.aboutToQuit.connect(backend.shutdown)

    engine = QQmlApplicationEngine()
    setup_engine(engine)
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(QUrl.fromLocalFile(str(HERE / "main.qml")))
    if not engine.rootObjects():
        print("Failed to load QML")
        return -1
    if "--demo" in sys.argv:
        backend.demo = True

    code = app.exec()
    del engine  # tear down QML before the backend it binds to
    return code


if __name__ == "__main__":
    sys.exit(main())
