"""3D scene helpers: QTM markers, bones, rigid bodies and skeletons for Qt Quick 3D apps.

This package is the data layer and needs only PySide6-Essentials (QtCore /
QtGui). Drawing it takes Qt Quick 3D, which is in PySide6-Addons:

    pip install "qtm-rt-pyside6[scene]"

and then :mod:`qtm_rt_pyside6.scene.quick3d` plus the ``Qualisys.Scene`` QML
module. A small app:

    connection = QTMConnection()
    scene = QtmScene(connection)
    ...
    engine = QQmlApplicationEngine()
    setup_engine(engine)  # from qtm_rt_pyside6.scene.quick3d
    engine.rootContext().setContextProperty("qtmScene", scene)
    # QML: import Qualisys.Scene ... QtmView { scene: qtmScene }
"""

from pathlib import Path

from .demo import DemoSource, demo_frame, demo_parameters
from .frame import SceneFrame, unlabeled_name
from .math3d import AXIS_UPWARDS, MISSING, AxisMapping, qtm_to_scene, rotate, scene_to_qtm
from .parameters import (
    RigidBodyDef,
    SceneParameters,
    Settings3D,
    SkeletonDef,
    parse_3d,
    parse_6d,
    parse_parameters,
    parse_skeletons,
    qtm_color,
)
from .scene import DEFAULT_COMPONENTS, PARAMETER_EVENTS, PointModel, QtmScene
from .skeleton import (
    JOINT_COLOR,
    KEEL_COLOR,
    SIDE_COLORS,
    bone_width,
    keel_axis,
    side_of,
    skeleton_bones,
    skeleton_frame,
    skeleton_joints,
    skeleton_poses,
)
from .theme import apply_theme, dark_palette, load_fonts

# The Qualisys.Scene QML module ships inside the package; add this to the QML import path
QML_IMPORT_PATH = Path(__file__).resolve().parent / "qml"

__all__ = [
    "AXIS_UPWARDS",
    "DEFAULT_COMPONENTS",
    "JOINT_COLOR",
    "KEEL_COLOR",
    "MISSING",
    "PARAMETER_EVENTS",
    "QML_IMPORT_PATH",
    "SIDE_COLORS",
    "AxisMapping",
    "DemoSource",
    "PointModel",
    "QtmScene",
    "RigidBodyDef",
    "SceneFrame",
    "SceneParameters",
    "Settings3D",
    "SkeletonDef",
    "apply_theme",
    "bone_width",
    "dark_palette",
    "demo_frame",
    "demo_parameters",
    "keel_axis",
    "load_fonts",
    "parse_3d",
    "parse_6d",
    "parse_parameters",
    "parse_skeletons",
    "qtm_color",
    "qtm_to_scene",
    "rotate",
    "scene_to_qtm",
    "side_of",
    "skeleton_bones",
    "skeleton_frame",
    "skeleton_joints",
    "skeleton_poses",
    "unlabeled_name",
]
