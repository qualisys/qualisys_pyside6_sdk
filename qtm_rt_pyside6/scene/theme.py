"""A light QTM look for Qt Quick apps, without branding.

Neutral grays of QTM's dark UI, Montserrat for labels and Open Sans for text,
flat controls, and checked controls in light gray rather than a color. The QML
side is the ``QtmTheme`` singleton in ``Qualisys.Scene``; this module sets up
the application around it:

    apply_theme(app)            # Fusion style, dark palette, Open Sans
    load_fonts(Path("fonts"))   # optional .ttf / .otf drop-in folder

and in QML, each window takes the theme's palette for the standard controls:

    ApplicationWindow { palette: QtmTheme.palette }

The fonts are used when installed; otherwise drop their .ttf / .otf files into
a folder and pass it to load_fonts(). They are not bundled with the SDK.
Without them Qt falls back to the system font.
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette

# The same values as the QtmTheme singleton
COLORS = {
    "bg": "#1f1f1f",  # panels
    "bgBar": "#1a1a1a",  # header, footer, tool strips
    "bgInset": "#151515",  # 3D view, logs
    "line": "#2a2a2a",  # dividers
    "lineStrong": "#3a3a3a",  # borders
    "text": "#ffffff",
    "muted": "#a0a0a0",  # secondary text
    "overline": "#767676",  # section labels, disabled text
    "neutral": "#e0e0e0",  # switches, sliders, checked controls
    "primary": "#da291c",  # the one primary action, alarms
}
DISPLAY_FONT = "Montserrat"
BODY_FONT = "Open Sans"


def dark_palette() -> QPalette:
    """QPalette with the theme's neutral grays; selection in light gray rather than a color.

    The same colors as QtmTheme.palette, which is what Qt Quick Controls need (see apply_theme())."""
    p = QPalette()
    colors = {
        QPalette.Window: "#1f1f1f",
        QPalette.WindowText: "#ffffff",
        QPalette.Base: "#151515",
        QPalette.AlternateBase: "#242424",
        QPalette.Text: "#ffffff",
        QPalette.Button: "#2a2a2a",
        QPalette.ButtonText: "#ffffff",
        QPalette.BrightText: "#ffffff",
        QPalette.Highlight: "#e0e0e0",
        QPalette.HighlightedText: "#1a1a1a",
        QPalette.Link: "#e0e0e0",
        QPalette.ToolTipBase: "#242424",
        QPalette.ToolTipText: "#ffffff",
        QPalette.PlaceholderText: "#767676",
        QPalette.Light: "#3a3a3a",
        QPalette.Midlight: "#303030",
        QPalette.Mid: "#242424",
        QPalette.Dark: "#0e0e0e",
        QPalette.Shadow: "#000000",
    }
    accent = getattr(QPalette, "Accent", None)  # Qt 6.6 and later
    if accent is not None:
        colors[accent] = "#e0e0e0"
    for role, color in colors.items():
        p.setColor(role, QColor(color))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor("#767676"))
    return p


def load_fonts(*directories) -> list[str]:
    """Register the .ttf / .otf files in these folders with Qt; returns the families added.

    Missing folders are skipped, so `load_fonts(Path(__file__).parent / "fonts")`
    is safe whether or not the user dropped any fonts there."""
    families = []
    for directory in directories:
        directory = Path(directory)
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.[ot]tf")):
            font_id = QFontDatabase.addApplicationFont(str(path))
            if font_id >= 0:
                families += QFontDatabase.applicationFontFamilies(font_id)
    return list(dict.fromkeys(families))


def apply_theme(app, *, style: str = "Fusion", point_size: int = 9):
    """Fusion style, the dark color scheme, the dark palette and Open Sans for a QGuiApplication.

    Call it before creating the QML engine: Qt Quick Controls pick their style once.

    Qt Quick Controls don't use the application palette set here: they start
    from their style's palette, which for Fusion is the platform's. Give each
    QML window the theme's palette:

        ApplicationWindow { palette: QtmTheme.palette }

    The dark color scheme (Qt 6.8 and later, where the platform supports it)
    covers what that palette doesn't reach, such as the title bar."""
    from PySide6.QtQuickControls2 import QQuickStyle  # Essentials, but only needed here

    if style:
        QQuickStyle.setStyle(style)
    hints = app.styleHints()
    if hasattr(hints, "setColorScheme"):  # Qt 6.8 and later
        hints.setColorScheme(Qt.ColorScheme.Dark)
    app.setPalette(dark_palette())
    app.setFont(QFont([BODY_FONT, "Segoe UI", "Helvetica Neue", "Arial"], point_size))
