# Changelog

All notable changes to the **ScanSlicer** project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.5.0] - 2026-11-18

### Added
- **Edge Trim Slider & Automatic White-Shim Shaving (`app/detector.py`, `app/sidebar.py`)**:
  - Added an **Edge Trim** slider (`0–25 px`, default `3 px`, persisted via `QSettings`) under **Auto Detection** to uniformly inset all 4 edges of detected boxes.
  - Added automatic white-border shaving (`_trim_white_edge_slivers`) to step edges inward past residual white scanner shims before applying the trim inset.
- **Delete Scanned Image Button (`app/main_window.py`, `app/canvas_view.py`)**:
  - Added **🗑 Delete Scan** to the main toolbar to delete the current scan file from disk (with confirmation) and return to the drop screen.
- **Skip Export Confirmation Option (`app/export_dialog.py`)**:
  - Added **"Disable confirmation dialog after exporting"** checkbox, persisted via `QSettings`, reporting completion in the status bar instead.

### Improved
- **Narrow & Zero-Gap Photo Splitting (`app/detector.py`)**:
  - Added `_split_oversized_contour` to recursively split merged multi-photo contours along their strongest horizontal/vertical dividing seam without affecting normal gap-separated detections.
- **Screen-Scaled Crop Handles (`app/crop_item.py`, `app/canvas_view.py`)**:
  - Scaled corner handles, edge handles, rotation stem/handle, borders, hit-test radii, and labels by the viewport zoom factor so controls stay a consistent screen-pixel size across all image resolutions.
- **Panning Past Image Edges (`app/canvas_view.py`)**:
  - Added padded `QGraphicsScene` bounds (`_update_padded_scene_rect`) so you can pan past any edge of the scanned image when zoomed in.
- **Export & Toolbar UX (`app/export_dialog.py`, `app/main_window.py`, `app/canvas_view.py`)**:
  - Persisted the **"Open output folder when finished"** checkbox state via `QSettings`.
  - Automatically unchecks **➕ Add Box** after drawing a manual box.
  - Renamed **🗑 Delete Selected** to **➖ Remove Selected Box**.

---

## [1.4.2] - 2026-11-16

### Improved
- **Smart Date Selector (`app/sidebar.py`, `app/styles.py`, `assets/chevron_down.svg`)**:
  - Replaced `QDateEdit` in both **Batch Date Setter** and each **Photo Card** with a custom `SmartDatePicker` featuring dedicated **Year** (editable dropdown `1900–2030+`, direct typing `1850–2100`), **Month** (`01 Jan`–`12 Dec`), and **Day** (auto-clamped to valid days per month/year) dropdown selectors.
  - Added a dark-themed `QCalendarWidget` popup button (`📅`) and crisp SVG dropdown chevrons (`assets/chevron_down.svg`).
  - Placed **Apply to All** on the **Batch Date Setter** header row so the date picker spans the full sidebar width cleanly.

---

## [1.4.0] - 2026-11-16

### Improved
- **Photo Detection Engine (`app/detector.py`)**:
  - Anchored LAB color-distance thresholding to the measured platen noise floor (with a bright-pixel fallback when photos touch the outer scan border), preventing global Otsu from erasing off-white borders, light grey portraits, and bright skies.
  - Switched to `cv2.RETR_EXTERNAL` with `3×3` morphological closing and box-area NMS so inner photo details never replace outer photo boundaries.
  - Added oversized-contour splitting via `3×3` morphological opening on `mask_diff` to separate tight multi-photo grids across narrow gutters.
  - Fixed `snap_rect_angle` to swap `w` and `h` whenever normalizing `angle` by `±90°`, preventing portrait photos from being rotated sideways.

### Changed
- **Project Structure & Cross-Platform Launchers**:
  - Moved application entry point to `app/main.py`.
  - Added Linux/macOS install and run `.sh` scripts alongside Windows `.bat` scripts and `releases\Compile EXE.bat` (outputs `releases\ScanSlicer.exe`).
  - Updated `.gitignore` for PyInstaller/build artifacts, Python tool caches, and Windows metadata.
  - Updated `README.md` and `CHANGELOG.md` branding to **ScanSlicer**.

---

## [1.3.0] - 2026-11-13

### Added
- **Standalone Windows Executable (`releases\ScanSlicer.exe`)**:
  - Full single-file executable distribution compiled with PyInstaller that runs on any Windows 10/11 machine without needing Python, pip, or administrator privileges.
  - Custom 3D application icon embedded directly into the `.exe` binary.
  - Bundled high-DPI assets, OpenCV C++ libraries, Qt6 runtimes, and piexif metadata helpers with runtime extraction via `sys._MEIPASS`.
- **One-Click Executable Builder (`releases\Compile EXE.bat`)**:
  - Automated script that cleans prior builds, packages assets and icons, and produces a freshly compiled `releases\ScanSlicer.exe`.
- **Automated Python Installation via `winget` in Batch Launchers**:
  - `Run ScanSplitter with Console.bat` (and alias `start.bat`) now performs multi-location Python discovery across `PATH`, `py` launcher, and local user/system installation paths.
  - If Python is not present on the machine, the script automatically triggers a silent installation of Python 3.12 using Windows Package Manager (`winget`), immediately locates the new executable without requiring a Windows reboot, creates `.venv`, installs requirements, and launches the app.
- **Convenience Aliases**:
  - Added root `start.bat` and `run.bat` aliases to make launching effortless from any terminal or shortcut.

---

## [1.2.0] - 2026-11-13

### Added
- **Custom Modern 3D App Icon (`assets/icon.png` & `assets/icon.ico`)**:
  - High-resolution Fluent/macOS style 3D squircle desktop icon featuring a glowing scanner platen, luminous optical scan line, glossy photos lifting and separating, and neon cyan corner crop brackets.
  - Multi-resolution Windows icon asset (`icon.ico` bundling 16x16, 24x24, 32x32, 48x48, 64x64, 128x128, and 256x256 formats).
  - Explicit Windows `AppUserModelID` (`scansplitter.photo.cropper.v1`) registration via Windows Shell API so the custom icon appears on the Windows taskbar and Alt+Tab switcher rather than the generic Python icon.
  - Window titlebar branding and application welcome drop prompt graphic.

---

## [1.1.0] - 2026-11-12

### Added
- **Silent Windows Launchers (`run.bat` & `run_no_console.bat`)**:
  - Starts the application using `pythonw.exe` without keeping any background command prompt or terminal window open.
- **Automatic Fit in View on Image Load**:
  - The scanned image automatically scales to fit comfortably within the window upon loading or dropping.
- **Source Folder Default Export Location**:
  - The export dialog now defaults directly to the directory containing the source scan file.
- **Rectangular vs. Skewed Resize Toggle (`📐 Lock Rectangular` / `🔓 Free Skew`)**:
  - Toggles between rigid 90-degree orthogonal rectangular resizing and free quadrilateral unwarping.
  - When locked, dragging any of the 4 corner handles preserves strict 90-degree right angles with the opposite corner acting as the fixed anchor.
  - When unlocked, individual corners can be skewed freely to correct perspective keystoning on crooked or curved prints.
- **On-the-Fly `Shift` Key Modifier**:
  - Holding the `Shift` key while dragging any corner temporarily inverts the rectangular lock setting without requiring a toolbar click.
- **One-Click Corner Squaring / Straightening**:
  - `⏹ Square Box` in the main toolbar snaps the selected crop box into an exact 90-degree rectangle aligned with its primary axis.
  - `⏹ Square` button on each sidebar photo card to square individual photos directly.
  - `⏹ Square All` button in the sidebar header to orthogonalize all detected boxes simultaneously.
- **Multi-Button Canvas Panning**:
  - Panning is now supported via **Space + Left Click Drag**, **Middle Click Drag**, or **Right Click Drag**.

### Fixed
- **Eliminated Distorted Trapezoid Selections**:
  - Replaced arbitrary polygon approximation with true rotated bounding rectangles (`cv2.minAreaRect`). All detected photos now default to strict 90-degree right angles.
- **Angle Snapping for Level Scans**:
  - Small contour noise angles within ±3.0° automatically snap to level 0.0° rectangles, while genuine photo tilts are accurately preserved.
- **Resolved Overlapping & Merged Containers**:
  - Implemented hierarchical contour analysis and rotated rectangle intersection filtering to discard outer merged containers that enclose multiple photos, preventing overlapping boxes.
- **Calibrated Adaptive Sensitivity Range**:
  - Grounded detection thresholds in image-specific Otsu adaptive calculations so sensitivity 1 no longer shatters photos into jagged shapes and sensitivity 100 no longer selects the entire image.
  - Added a one-click `↺ 50` reset button and descriptive labels.
- Fixed `AttributeError: type object 'KeyboardModifier' has no attribute 'SpaceModifier'` when pressing mouse buttons on the canvas.
- Improved viewport bounds and handle drag responsiveness under high-DPI scaling.

---

## [1.0.0] - 2026-11-12

### Initial Release
- **Complete Architecture Rewrite**:
  - Built from scratch as a high-performance native desktop application with PyQt6, OpenCV, and Pillow.
- **Multi-Photo Scanner Bed Detection**:
  - Robust multi-method computer vision engine estimating platen background colors (light or dark platen lids).
  - Perceptual LAB color distance combined with Canny edge detection and morphology.
  - Minimum area rotated bounding box fitting with adjustable detection sensitivity.
- **Interactive QGraphics Canvas**:
  - Rotated crop boxes with 4 draggable corner handles, 4 edge resize handles, and an intuitive rotation handle.
  - Whole-box repositioning by dragging inside the selection.
  - Manual crop creation tool (`➕ Add Box`) for user-drawn selections.
- **Real-Time Magnifying Loupe View**:
  - High-precision live loupe widget (4x, 6x, 8x zoom) with center crosshairs and pixel coordinates to align corners down to the exact edge.
- **Photo Dates & EXIF Metadata**:
  - Individual date selection per photo card.
  - Global Batch Date setter ("Apply to All").
  - Automatic embedding into standard EXIF tags (`DateTimeOriginal`, `DateTimeDigitized`, `DateTime`).
- **High-Fidelity Perspective Extraction & Export**:
  - Perspective transforms at full scanner resolution to deskew and extract straightened photos.
  - Export to JPEG (with quality control) or lossless PNG.
  - Customizable filename formatting templates.
  - Automatic folder opening in Windows Explorer upon completion.
- **Windows Launcher**:
  - One-click `start.bat` launcher that automatically sets up and verifies the `.venv` virtual environment.

