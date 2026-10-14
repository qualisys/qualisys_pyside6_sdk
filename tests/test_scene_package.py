"""Packaging of the scene helpers: import isolation, the [scene] extra's error messages, QML files, PyInstaller hook."""

import re
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, distribution, entry_points
from pathlib import Path

import pytest

import qtm_rt_pyside6.scene as scene_package
from qtm_rt_pyside6.__pyinstaller import get_hook_dirs


def run_python(code: str) -> subprocess.CompletedProcess:
    """Run code in a fresh interpreter, so this test session's imports don't leak in."""
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)


def test_core_does_not_import_the_scene_package():
    result = run_python(
        "import sys, qtm_rt_pyside6\nprint(sorted(m for m in sys.modules if m.startswith('qtm_rt_pyside6.scene')))\n"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


def test_data_layer_needs_only_qtcore_and_qtgui():
    result = run_python(
        "import sys, qtm_rt_pyside6, qtm_rt_pyside6.scene\n"
        "print(sorted(m for m in sys.modules if m.startswith('PySide6.Qt')))\n"
    )
    assert result.returncode == 0, result.stderr
    modules = set(eval(result.stdout))
    assert "PySide6.QtQuick3D" not in modules
    assert modules <= {"PySide6.QtCore", "PySide6.QtGui", "PySide6.QtNetwork"}


def test_missing_addons_names_the_extra():
    result = run_python(
        "import importlib.abc, sys\n"
        "class NoQuick3D(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path, target=None):\n"
        "        if name == 'PySide6.QtQuick3D':\n"
        "            raise ImportError(\"No module named 'PySide6.QtQuick3D'\")\n"
        "sys.meta_path.insert(0, NoQuick3D())\n"
        "import qtm_rt_pyside6.scene\n"  # the data layer still works
        "try:\n"
        "    import qtm_rt_pyside6.scene.quick3d\n"
        "except ImportError as e:\n"
        "    print(e)\n"
    )
    assert result.returncode == 0, result.stderr
    assert 'pip install "qtm-rt-pyside6[scene]"' in result.stdout
    assert "PySide6-Addons" in result.stdout


def test_old_pyside6_is_refused_clearly():
    result = run_python(
        "import PySide6\n"
        "PySide6.__version_info__, PySide6.__version__ = (6, 4, 3), '6.4.3'\n"
        "try:\n"
        "    import qtm_rt_pyside6.scene.quick3d\n"
        "except ImportError as e:\n"
        "    print(e)\n"
    )
    assert result.returncode == 0, result.stderr
    assert "6.5 or later" in result.stdout and "6.4.3" in result.stdout


class TestQmlModule:
    directory = scene_package.QML_IMPORT_PATH / "Qualisys" / "Scene"

    def qmldir_files(self) -> dict[str, str]:
        entries = {}
        for line in (self.directory / "qmldir").read_text().splitlines():
            m = re.match(r"(?:singleton\s+)?(\w+)\s+[\d.]+\s+(\S+\.qml)$", line.strip())
            if m:
                entries[m.group(1)] = m.group(2)
        return entries

    def test_every_qml_file_is_in_the_qmldir(self):
        listed = set(self.qmldir_files().values())
        on_disk = {p.name for p in self.directory.glob("*.qml")}
        assert listed == on_disk

    def test_module_name(self):
        assert (self.directory / "qmldir").read_text().splitlines()[0] == "module Qualisys.Scene"

    def test_public_types(self):
        expected = {"QtmView", "QtmCameraController", "MarkerLayer", "BoneLayer", "SkeletonLayer", "LabelOverlay"}
        expected |= {"Floor", "QtmAxes", "QtmTheme", "QtmButton", "QtmSwitch", "QtmSection", "RigidBodyLayer"}
        assert set(self.qmldir_files()) == expected


class TestPyInstallerHook:
    def test_hook_dir(self):
        (directory,) = get_hook_dirs()
        assert (Path(directory) / "hook-qtm_rt_pyside6.scene.quick3d.py").is_file()

    def test_entry_point(self):
        try:
            distribution("qtm-rt-pyside6")
        except PackageNotFoundError:
            pytest.skip("package not installed (pip install -e .)")
        hooks = {ep.value for ep in entry_points(group="pyinstaller40", name="hook-dirs")}
        assert "qtm_rt_pyside6.__pyinstaller:get_hook_dirs" in hooks
