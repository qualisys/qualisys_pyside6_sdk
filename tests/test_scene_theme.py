"""QtmTheme's palette for Qt Quick Controls, and theme.py. Needs only PySide6-Essentials.

Qt Quick Controls don't use the application palette that apply_theme() sets:
they start from their style's, which for Fusion is the platform's. Windows take
QtmTheme.palette instead.
"""

import json
import subprocess
import sys
from unittest import mock

import pytest
from PySide6.QtCore import Q_RETURN_ARG, QCoreApplication, QEvent, QMetaObject, Qt, QUrl
from PySide6.QtGui import QPalette
from PySide6.QtQml import QQmlComponent, QQmlEngine

from qtm_rt_pyside6.scene import QML_IMPORT_PATH, apply_theme, dark_palette
from qtm_rt_pyside6.scene.theme import COLORS

GROUPS = {"active": QPalette.Active, "inactive": QPalette.Inactive, "disabled": QPalette.Disabled}
ROLES = [role for role in QPalette.ColorRole if role not in (QPalette.NoRole, QPalette.NColorRoles)]


def qml_name(role: QPalette.ColorRole) -> str:
    """The role's name in QML: windowText for QPalette.WindowText."""
    return role.name[0].lower() + role.name[1:]


class Engine:
    """A QQmlEngine that finds Qualisys.Scene and collects QML warnings."""

    def __init__(self):
        self.engine = QQmlEngine()
        self.engine.addImportPath(str(QML_IMPORT_PATH))
        self.warnings: list[str] = []
        self.engine.warnings.connect(lambda ws: self.warnings.extend(w.toString() for w in ws))
        self.components = []  # an object lives as long as its component here
        self.objects = []

    def create(self, qml: str):
        component = QQmlComponent(self.engine)
        component.setData(qml.encode(), QUrl())
        obj = component.create()
        assert obj is not None, component.errorString()
        self.components.append(component)
        self.objects.append(obj)
        return obj

    def close(self):
        # The objects go before the engine they were created in
        for obj in self.objects:
            obj.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.objects.clear()
        self.components.clear()


@pytest.fixture
def engine(qtbot):
    e = Engine()
    yield e
    e.close()
    assert e.warnings == []


def call(obj, method: str):
    """Call a QML function that returns JSON."""
    return json.loads(QMetaObject.invokeMethod(obj, method, Q_RETURN_ARG("QVariant")))


def test_tokens_match_colors(engine):
    obj = engine.create(
        """
        import QtQuick
        import Qualisys.Scene
        QtObject {
            function report() {
                var colors = {}
                for (const name of NAMES)
                    colors[name] = QtmTheme[name].toString()
                return JSON.stringify(colors)
            }
        }
        """.replace("NAMES", json.dumps(list(COLORS)))
    )
    assert call(obj, "report") == COLORS


def test_palette_matches_dark_palette(engine):
    obj = engine.create(
        """
        import QtQuick
        import Qualisys.Scene
        QtObject {
            function report() {
                var palette = QtmTheme.palette
                var groups = {active: palette.active, inactive: palette.inactive, disabled: palette.disabled}
                var colors = {}
                for (const group in groups)
                    for (const name of NAMES)
                        if (name in groups[group])
                            colors[group + "." + name] = groups[group][name].toString()
                return JSON.stringify(colors)
            }
        }
        """.replace("NAMES", json.dumps([qml_name(role) for role in ROLES]))
    )
    colors = call(obj, "report")
    expected = dark_palette()
    compared = set()
    for group_name, group in GROUPS.items():
        for role in ROLES:
            if expected.isBrushSet(group, role):
                key = f"{group_name}.{qml_name(role)}"
                assert colors[key] == expected.color(group, role).name(), key
                compared.add(key)
    assert {"active.windowText", "inactive.base", "disabled.text"} <= compared


def test_window_palette_follows_token_overrides(engine):
    window = engine.create(
        """
        import QtQuick
        import Qualisys.Scene
        Window {
            palette: QtmTheme.palette
            function report() {
                return JSON.stringify({
                    windowText: palette.windowText.toString(),
                    disabledWindowText: palette.disabled.windowText.toString(),
                    base: palette.base.toString(),
                    text: QtmTheme.text.toString(),
                })
            }
            function override() { QtmTheme.text = "#ff0000"; QtmTheme.bgInset = "#00ff00" }
        }
        """,
    )
    before = call(window, "report")
    assert before["windowText"] == before["text"] == COLORS["text"]
    assert before["disabledWindowText"] == COLORS["overline"]
    assert before["base"] == COLORS["bgInset"]

    # A token changed at start-up, after the window took the palette, still reaches it
    QMetaObject.invokeMethod(window, "override")
    after = call(window, "report")
    assert after["windowText"] == after["text"] == "#ff0000"
    assert after["disabledWindowText"] == COLORS["overline"]
    assert after["base"] == "#00ff00"


def test_controls_take_qtmtheme_palette_after_apply_theme():
    # A fresh interpreter: apply_theme() picks the Qt Quick Controls style, which a process does once
    code = """
import json, sys
from PySide6.QtCore import QMetaObject, Q_RETURN_ARG
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from qtm_rt_pyside6.scene import QML_IMPORT_PATH, apply_theme

app = QGuiApplication(sys.argv)
apply_theme(app)
engine = QQmlApplicationEngine()
engine.addImportPath(str(QML_IMPORT_PATH))
engine.loadData(b'''
import QtQuick
import QtQuick.Controls
import Qualisys.Scene
ApplicationWindow {
    visible: false
    palette: QtmTheme.palette
    function report() {
        return JSON.stringify({
            label: label.color.toString(),
            windowText: palette.windowText.toString(),
            disabledLabel: disabledLabel.color.toString(),
            field: field.color.toString(),
            fieldBase: field.palette.base.toString(),
            text: QtmTheme.text.toString(),
            overline: QtmTheme.overline.toString(),
            bgInset: QtmTheme.bgInset.toString(),
        })
    }
    Column {
        Label { id: label; text: "label" }
        Label { id: disabledLabel; text: "disabled"; enabled: false }
        TextField { id: field; text: "field" }
    }
}
''')
print(QMetaObject.invokeMethod(engine.rootObjects()[0], "report", Q_RETURN_ARG("QVariant")))
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    colors = json.loads(result.stdout.strip().splitlines()[-1])
    assert colors["windowText"] == colors["text"]
    assert colors["label"] == colors["text"]
    assert colors["disabledLabel"] == colors["overline"]
    assert colors["field"] == colors["text"]
    assert colors["fieldBase"] == colors["bgInset"]


def test_apply_theme_asks_for_the_dark_color_scheme():
    app = mock.MagicMock()
    apply_theme(app, style="")
    app.styleHints.return_value.setColorScheme.assert_called_once_with(Qt.ColorScheme.Dark)
    app.setPalette.assert_called_once()
