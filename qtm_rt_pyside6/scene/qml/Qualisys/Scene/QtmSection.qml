import QtQuick

// Section label: Montserrat bold, small spaced capitals (an "overline")
Text {
    color: QtmTheme.overline
    font.family: QtmTheme.displayFont
    font.weight: Font.Bold
    font.pixelSize: QtmTheme.sectionFontSize
    font.letterSpacing: QtmTheme.sectionLetterSpacing
    font.capitalization: Font.AllUppercase
    topPadding: 8
}
