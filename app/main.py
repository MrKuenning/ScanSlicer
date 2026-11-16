"""
ScanSplitter Application Entry Point.
"""

import ctypes
import sys
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from app.main_window import MainWindow


def main():
    # Set explicit AppUserModelID on Windows for taskbar icon grouping
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "scansplitter.photo.cropper.v1"
            )
        except Exception:
            pass

    # Enable high-DPI support
    if hasattr(Qt.HighDpiScaleFactorRoundingPolicy, "PassThrough"):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

    app = QApplication(sys.argv)
    app.setApplicationName("ScanSplitter")
    app.setOrganizationName("ScanSplitter")

    # Set application icon
    from app import get_asset_path
    icon_ico = get_asset_path("icon.ico")
    icon_png = get_asset_path("icon.png")
    icon_path = icon_ico if icon_ico.exists() else icon_png
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()

    # Optional: If file path passed as CLI argument, open it directly
    if len(sys.argv) > 1:
        initial_file = sys.argv[1]
        if Path(initial_file).exists():
            window.load_image_file(initial_file)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

