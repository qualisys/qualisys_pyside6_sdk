"""PyInstaller hooks, registered through the ``pyinstaller40`` entry point.

They bundle the ``Qualisys.Scene`` QML module with apps that use
:mod:`qtm_rt_pyside6.scene.quick3d`, so frozen apps need no extra --add-data.
"""

from pathlib import Path


def get_hook_dirs() -> list[str]:
    return [str(Path(__file__).resolve().parent)]
