"""Qt Quick 3D side of the scene helpers: the Qualisys.Scene QML module and its Python types.

Needs Qt Quick 3D, which is in PySide6-Addons:

    pip install "qtm-rt-pyside6[scene]"

Typical use:

    engine = QQmlApplicationEngine()
    setup_engine(engine)  # registers the types, adds the QML import path
    engine.rootContext().setContextProperty("qtmScene", scene)

and in QML ``import Qualisys.Scene`` for QtmView, the layers and QtmTheme.
The Python types are registered under ``Qualisys.Scene.Native`` (1.0).

Render thread: Qt calls the instance tables' getInstanceBuffer() from the
scene graph's render thread, which then needs Python's GIL. A Python call that
blocks the GUI thread until the render thread is done therefore deadlocks:
QTest.qWait() and QQuickWindow.grabWindow() do. app.exec(),
QCoreApplication.processEvents(), pytest-qt's qtbot.wait() / waitSignal() and
the asynchronous QQuickItem.grabToImage() are fine. Setting the environment
variable QSG_RENDER_LOOP=basic (render on the GUI thread) avoids it altogether.
"""

import PySide6

MIN_PYSIDE6 = (6, 5)
INSTALL_HINT = 'pip install "qtm-rt-pyside6[scene]"'

if tuple(PySide6.__version_info__[:2]) < MIN_PYSIDE6:
    raise ImportError(
        f"qtm_rt_pyside6.scene.quick3d needs PySide6 {'.'.join(map(str, MIN_PYSIDE6))} or later "
        f"(ExtendedSceneEnvironment, instancing); found {PySide6.__version__}. Upgrade with: {INSTALL_HINT}"
    )

try:
    from PySide6 import QtQuick3D  # noqa: F401 - in PySide6-Addons
except ImportError as e:
    raise ImportError(
        "qtm_rt_pyside6.scene.quick3d needs Qt Quick 3D, which is in PySide6-Addons. "
        f"Install the SDK with the scene extra: {INSTALL_HINT}"
    ) from e

from PySide6.QtQml import qmlRegisterType  # noqa: E402

from .. import QML_IMPORT_PATH  # noqa: E402
from ..theme import apply_theme, dark_palette, load_fonts  # noqa: E402
from ._geometry import BONE_STYLES, GridGeometry, KeelBoneGeometry, keel_bone_triangles  # noqa: E402
from ._instancing import (  # noqa: E402
    AXIS_COLORS,
    AxesInstancing,
    BoneInstancing,
    MarkerInstancing,
    RigidBodyInstancing,
    SceneInstancing,
    SkeletonInstancing,
)

NATIVE_URI = "Qualisys.Scene.Native"

_TYPES = (
    KeelBoneGeometry,
    GridGeometry,
    MarkerInstancing,
    BoneInstancing,
    SkeletonInstancing,
    RigidBodyInstancing,
    AxesInstancing,
)
_registered = False


def register_qml_types():
    """Make the geometry and instancing types available to QML as `import Qualisys.Scene.Native`."""
    global _registered
    if _registered:
        return
    for cls in _TYPES:
        qmlRegisterType(cls, NATIVE_URI, 1, 0, cls.__name__)
    _registered = True


def setup_engine(engine):
    """Get a QQmlEngine ready for `import Qualisys.Scene`: register the types and add the import path."""
    register_qml_types()
    path = str(QML_IMPORT_PATH)
    if path not in engine.importPathList():
        engine.addImportPath(path)
    return engine


__all__ = [
    "AXIS_COLORS",
    "BONE_STYLES",
    "INSTALL_HINT",
    "NATIVE_URI",
    "QML_IMPORT_PATH",
    "AxesInstancing",
    "BoneInstancing",
    "GridGeometry",
    "KeelBoneGeometry",
    "MarkerInstancing",
    "RigidBodyInstancing",
    "SceneInstancing",
    "SkeletonInstancing",
    "apply_theme",
    "dark_palette",
    "keel_bone_triangles",
    "load_fonts",
    "register_qml_types",
    "setup_engine",
]
