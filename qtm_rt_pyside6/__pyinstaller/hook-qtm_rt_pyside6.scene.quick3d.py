# Bundle the Qualisys.Scene QML module (qtm_rt_pyside6/scene/qml) with apps that
# import qtm_rt_pyside6.scene.quick3d. Qt's own QML modules (QtQuick3D and its
# Helpers) are collected by PyInstaller's PySide6 hooks.
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("qtm_rt_pyside6.scene", includes=["qml/**/*"])
hiddenimports = ["PySide6.QtQuick3D", "PySide6.QtQuickControls2"]
