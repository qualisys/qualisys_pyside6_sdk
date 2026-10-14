pragma Singleton
import QtQuick

// Look tokens: the neutral grays of QTM's dark UI, Montserrat labels + Open Sans
// text, flat 4 px controls, and the red only as punctuation (the one primary
// action, alarms). No logos, no product naming.
//
// Every token is a plain property, so an app can override it at start-up:
//     Component.onCompleted: QtmTheme.primary = "#0baccd"
QtObject {
    // Surfaces
    property color bg: "#1f1f1f"            // panels
    property color bgBar: "#1a1a1a"         // header, footer, tool strips
    property color bgInset: "#151515"       // 3D view, logs
    property color bgOverlay: "#e61a1a1a"   // strips floating over the 3D view
    property color line: "#2a2a2a"          // dividers
    property color lineStrong: "#3a3a3a"    // borders
    property color hover: "#333333"         // hovered flat control
    property color disabledFill: "#242424"
    property color selectedRow: "#323232"
    property color hoverRow: "#272727"

    // Text
    property color text: "#ffffff"
    property color muted: "#a0a0a0"         // secondary text
    property color overline: "#767676"      // section labels, disabled text

    // Accents
    property color neutral: "#e0e0e0"       // switches, sliders, checked controls
    property color primary: "#da291c"       // the one primary action
    property color primaryHover: "#be1e15"
    property color primaryPressed: "#801811"
    property color alarm: "#e15449"         // alarm text, readable on dark
    property color success: "#a4d9b3"

    // Type
    property string displayFont: "Montserrat"   // headings, buttons, section labels
    property string bodyFont: "Open Sans"
    property string monoFont: Qt.platform.os === "windows" ? "Consolas"
                            : Qt.platform.os === "osx" ? "Menlo" : "DejaVu Sans Mono"
    property int fontSize: 12
    property int smallFontSize: 11
    property int sectionFontSize: 10
    property real sectionLetterSpacing: 1.4
    property int radius: 4
    property int controlHeight: 28

    // 3D scene
    property color sceneBackground: "#151515"
    property color floor: "#1c1c1c"
    property color grid: "#262626"
    property color gridMajor: "#323232"
    property var axisColors: ["#e15449", "#59b36b", "#5d82ea"]   // X, Y, Z
    property color unlabeled: "#767676"
    property color joint: "#ffffff"
    property color keel: "#f2f2f2"           // the ridge stripe on keeled bones
    property color left: "#456ce2"           // skeleton sides, as QTM colors markers
    property color right: "#f0c844"
    property color center: "#a0a0a0"
    property color labelText: "#ffffff"
    property color labelOutline: "#000000"
}
