"""
Modern Dark Theme stylesheet for ScanSplitter PyQt6 application.
"""

DARK_THEME_QSS = """
QMainWindow {
    background-color: #14171f;
}

QWidget {
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    color: #e2e8f0;
}

/* ToolBar Styling */
QToolBar {
    background-color: #1a1e27;
    border-bottom: 1px solid #282f3d;
    spacing: 5px;
    padding: 6px 10px;
}

QToolButton {
    background-color: #242a36;
    color: #f1f5f9;
    border: 1px solid #363e4f;
    border-radius: 6px;
    padding: 5px 9px;
    font-weight: 600;
    font-size: 12px;
}

QToolButton:disabled {
    background-color: #1c2029;
    color: #5a6578;
    border-color: #272d3a;
}

QToolButton#DangerBtn {
    background-color: #4a1e24;
    color: #ff8a8a;
    border: 1px solid #8a2c36;
}
QToolButton#DangerBtn:hover {
    background-color: #e53935;
    color: #ffffff;
    border-color: #ff5252;
}
QToolButton#DangerBtn:disabled {
    background-color: #1c2029;
    color: #5a6578;
    border-color: #272d3a;
}

QToolButton#SuccessBtn {
    background-color: #1b4332;
    color: #80ed99;
    border: 1px solid #2d6a4f;
}
QToolButton#SuccessBtn:hover, QToolButton#SuccessBtn:checked {
    background-color: #00c853;
    color: #0f172a;
    border-color: #00e676;
}
QToolButton#SuccessBtn:disabled {
    background-color: #1c2029;
    color: #5a6578;
    border-color: #272d3a;
}

QToolButton:hover {
    background-color: #00d2ff;
    color: #0f172a;
    border-color: #00d2ff;
}

QToolButton:pressed {
    background-color: #00a0cc;
}

QToolButton:checked {
    background-color: #00d2ff;
    color: #0f172a;
    border-color: #00d2ff;
}

/* ScrollBars */
QScrollBar:vertical {
    background: #14171f;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #363e4f;
    min-height: 25px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #00d2ff;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Sliders */
QSlider::groove:horizontal {
    height: 6px;
    background: #2b3342;
    border-radius: 3px;
}

QSlider::sub-page:horizontal {
    background: #00d2ff;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #ffffff;
    border: 2px solid #00d2ff;
    width: 14px;
    margin-top: -4px;
    margin-bottom: -4px;
    border-radius: 7px;
}

/* Status Bar */
QStatusBar {
    background-color: #1a1e27;
    color: #94a3b8;
    font-size: 11px;
    border-top: 1px solid #282f3d;
}

/* Tooltips */
QToolTip {
    background-color: #1e2430;
    color: #ffffff;
    border: 1px solid #00d2ff;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 11px;
}

/* Dark Calendar Popup */
QCalendarWidget QWidget {
    background-color: #1a1e27;
    color: #e2e8f0;
    alternate-background-color: #212733;
}
QCalendarWidget QToolButton {
    background-color: #242a36;
    color: #f1f5f9;
    border: 1px solid #363e4f;
    border-radius: 4px;
    padding: 4px 8px;
    margin: 2px;
}
QCalendarWidget QToolButton:hover {
    background-color: #00d2ff;
    color: #0f172a;
}
QCalendarWidget QAbstractItemView:enabled {
    background-color: #161920;
    color: #e2e8f0;
    selection-background-color: #00d2ff;
    selection-color: #0f172a;
}
"""

