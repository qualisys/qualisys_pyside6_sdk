"""
Minimal 3D viewer - QTM markers, bones, rigid bodies and skeletons in a window

    pip install "qtm-rt-pyside6[scene]"
    python scene_minimal.py [host]       # QTM at host (default 127.0.0.1)
    python scene_minimal.py --demo       # simulated data, no QTM needed

Mouse as in QTM: left-drag orbits, right-drag pans, the wheel zooms.
"""

import sys

from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from qtm_rt_pyside6 import QTMConnection
from qtm_rt_pyside6.scene import DemoSource, QtmScene, apply_theme
from qtm_rt_pyside6.scene.quick3d import setup_engine

QML = b"""
import QtQuick
import Qualisys.Scene

Window {
    width: 1280; height: 800; visible: true; title: "QTM 3D"
    QtmView { anchors.fill: parent; scene: qtmScene }
}
"""

app = QGuiApplication(sys.argv)
apply_theme(app)
connection = QTMConnection()
scene = QtmScene(connection)  # asks QTM for its parameters and streams what the view needs
demo = DemoSource(scene)

engine = QQmlApplicationEngine()
setup_engine(engine)
engine.rootContext().setContextProperty("qtmScene", scene)
engine.loadData(QML)

if "--demo" in sys.argv:
    demo.start()
else:
    connection.connectToHost(next((a for a in sys.argv[1:] if not a.startswith("-")), "127.0.0.1"))
sys.exit(app.exec())
