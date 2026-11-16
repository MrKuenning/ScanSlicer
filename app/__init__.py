"""
ScanSplitter Package
"""
import sys
from pathlib import Path

__version__ = "1.3.0"


def get_asset_path(relative_name: str) -> Path:
    """Resolve an asset path reliably in both development and PyInstaller bundled environments."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundled_base = Path(sys._MEIPASS)
        path = bundled_base / relative_name
        if path.exists():
            return path
        path_assets = bundled_base / "assets" / relative_name
        if path_assets.exists():
            return path_assets

    root_base = Path(__file__).resolve().parent.parent
    path = root_base / relative_name
    if path.exists():
        return path
    path_assets = root_base / "assets" / relative_name
    if path_assets.exists():
        return path_assets
    return path

