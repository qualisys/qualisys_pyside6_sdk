"""Render smoke test: QtmView with demo data, without QML warnings. Needs PySide6-Addons.

The tests render with the basic (GUI thread) render loop. The default threaded
loop is what apps use, but it stalls when the display is asleep or the session
is locked, which made these tests hang now and then. With the threaded loop Qt
calls the instance tables' getInstanceBuffer() from the render thread, which
then needs the GIL; Python calls that block the GUI thread on the render thread
deadlock there: QTest.qWait() and QQuickWindow.grabWindow(). So these tests
also wait with qtbot.wait() / qtbot.waitSignal() and grab with the asynchronous
grabToImage(), which are safe with either loop.

The tests that show a window skip where Qt Quick 3D cannot render: no frame,
a scene graph error, or a Qt Quick renderer that is not based on QRhi (e.g. the
software renderer Qt falls back to with QT_QPA_PLATFORM=offscreen and no GPU).
The hidden-window test runs everywhere.
"""

import os

import pytest

# Before any QQuickWindow exists: the render loop is chosen once per process
os.environ.setdefault("QSG_RENDER_LOOP", "basic")

pytest.importorskip("PySide6.QtQuick3D", reason='needs PySide6-Addons: pip install "qtm-rt-pyside6[scene]"')

from PySide6.QtCore import QObject  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QSGRendererInterface  # noqa: E402

from qtm_rt_pyside6.scene import DemoSource, QtmScene  # noqa: E402
from qtm_rt_pyside6.scene.quick3d import setup_engine  # noqa: E402

WINDOW = b"""
import QtQuick
import Qualisys.Scene

Window {
    width: 900
    height: 600
    visible: %s
    color: QtmTheme.bgInset

    QtmView {
        objectName: "view"
        anchors.fill: parent
        scene: qtmScene
        labelMode: "all"
    }
}
"""


class Harness:
    def __init__(self, visible: bool):
        self.warnings: list[str] = []
        self.scene = QtmScene()
        self.demo = DemoSource(self.scene)
        self.engine = QQmlApplicationEngine()
        self.engine.warnings.connect(lambda ws: self.warnings.extend(w.toString() for w in ws))
        setup_engine(self.engine)
        self.engine.rootContext().setContextProperty("qtmScene", self.scene)
        self.engine.loadData(WINDOW % (b"true" if visible else b"false"))
        assert self.engine.rootObjects(), self.warnings
        self.window = self.engine.rootObjects()[0]
        self.view = self.window.findChild(QObject, "view")

    def close(self):
        self.demo.stop()
        self.window.close()
        self.engine.deleteLater()  # tear down QML before the scene it binds to


def grab(qtbot, window):
    """The window's content, grabbed asynchronously (grabWindow() would deadlock, see above)."""
    result = window.contentItem().grabToImage()
    with qtbot.waitSignal(result.ready, timeout=5000):
        pass
    return result.image()


@pytest.fixture
def hidden(qtbot):
    h = Harness(visible=False)
    yield h
    h.close()


def renderer_problem(window, qtlog) -> str | None:
    """Why Qt Quick 3D cannot draw in this window, or None. Frames can still swap without it."""
    api = window.rendererInterface().graphicsApi()
    if not QSGRendererInterface.isApiRhiBased(api):
        return f"Qt Quick uses the {api.name} renderer, not a QRhi-based one"
    if api == QSGRendererInterface.GraphicsApi.Null:
        return "Qt Quick uses QRhi's Null backend, which draws nothing"
    if any("Qt Quick 3D is not functional" in record.message for record in qtlog.records):
        return "Qt Quick 3D reports that it is not functional"
    return None


@pytest.fixture
def shown(qtbot, qtlog):
    h = Harness(visible=True)
    errors = []
    h.window.sceneGraphError.connect(lambda _error, message: errors.append(message))
    try:
        with qtbot.waitSignal(h.window.frameSwapped, timeout=10000):
            pass
    except Exception:  # noqa: BLE001 - pytest-qt's TimeoutError
        errors.append("no frame rendered")
    if not errors:
        problem = renderer_problem(h.window, qtlog)
        if problem:
            errors.append(problem)
    if errors:
        h.close()
        pytest.skip(f"Qt Quick 3D cannot render here: {errors[0]}")
    yield h
    h.close()


def test_qml_loads_without_warnings(qtbot, hidden):
    hidden.demo.start()
    qtbot.wait(300)
    assert hidden.view is not None
    assert hidden.warnings == []


def test_only_visible_layers_are_pickable(hidden):
    def kinds():
        return sorted(hidden.view.property("pickableKinds").toVariant())

    assert kinds() == ["body", "joint", "marker", "unlabeled"]
    hidden.view.setProperty("showUnlabeled", False)
    assert kinds() == ["body", "joint", "marker"]
    hidden.view.setProperty("showUnlabeled", True)
    hidden.view.setProperty("showMarkers", False)
    assert kinds() == ["body", "joint"]  # unlabeled markers are drawn by the marker layer
    hidden.view.setProperty("showSkeletons", False)
    hidden.view.setProperty("showRigidBodies", False)
    assert kinds() == []


def test_renders_demo_without_warnings(qtbot, shown):
    shown.demo.start()
    with qtbot.waitSignal(shown.scene.firstData, timeout=3000):
        pass
    shown.scene.highlight(["L_Elbow", "Demo:LeftForeArm", "Wand"])
    qtbot.wait(800)
    image = grab(qtbot, shown.window)
    assert shown.warnings == []
    assert not image.isNull()

    # Flat background: the image-based light does not show as a sky
    corner = image.pixelColor(3, 3)
    assert max(abs(corner.red() - 0x15), abs(corner.green() - 0x15), abs(corner.blue() - 0x15)) <= 3

    # Blue (left) and gold (right) skeleton bones are on screen
    blue = gold = 0
    for y in range(0, image.height(), 3):
        for x in range(0, image.width(), 3):
            c = image.pixelColor(x, y)
            r, g, b = c.red(), c.green(), c.blue()
            blue += b > r + 50 and b > g + 20
            gold += r > b + 60 and g > b + 40
    assert blue > 20 and gold > 20


@pytest.mark.parametrize("style", ["keeled", "octahedral", "capsule", "stick"])
def test_bone_styles_and_axes(qtbot, shown, style):
    shown.demo.start()
    shown.view.setProperty("boneStyle", style)
    shown.view.setProperty("axesMode", "all")
    qtbot.wait(400)
    shown.view.setProperty("axesMode", "selected")
    shown.scene.highlight(["Demo"])
    qtbot.wait(300)
    assert shown.warnings == []
