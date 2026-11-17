# ScanSlicer

<p align="center">
  <img src="assets/icon.png" width="160" height="160" alt="ScanSlicer App Icon" />
</p>

A modern native desktop application for automatically detecting, deskewing, and splitting multiple crooked photos from flatbed scanner bed images.

![Version](https://img.shields.io/badge/version-1.4.0-blue.svg)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![PyQt6](https://img.shields.io/badge/UI-PyQt6-green)
![OpenCV](https://img.shields.io/badge/Vision-OpenCV-red)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)

---

## Installation & Running

### Windows

ScanSlicer can run as a **standalone zero-install executable** (no Python needed) or directly from source with **automated Python bootstrapping**:

#### 1. Standalone Executable (No Python Needed)
- Download the pre-built `ScanSlicer.exe` from **GitHub Releases** — Python, PyQt6, OpenCV, and all assets are bundled inside, so you can run it immediately on any Windows 10/11 PC.
- To compile the `.exe` yourself from source, run:
  ```text
  releases\Compile EXE.bat
  ```
  This outputs the standalone executable to `releases\ScanSlicer.exe`.

#### 2. Install & Run from Source
- **Install dependencies only** (creates `.venv` and installs `requirements.txt`; auto-installs Python 3.12 via `winget` if missing):
  ```text
  Install ScanSplitter Windows.bat
  ```
- **Silent launcher** (runs via `pythonw.exe` without a console window; auto-installs if `.venv` is missing):
  ```text
  Run ScanSplitter Windows.bat
  ```
- **Console launcher** (recommended for debugging; auto-installs if `.venv` is missing):
  ```text
  Run ScanSplitter Windows Console.bat
  ```

### Linux / macOS

Requires **Python 3.10+**.

- **Install dependencies only** (creates `.venv` and installs `requirements.txt`):
  ```bash
  bash "Install ScanSplitter Linux Mac.sh"
  ```
- **Run the app** (automatically runs `Install ScanSplitter Linux Mac.sh` if `.venv` is missing):
  ```bash
  bash "Run ScanSplitter Linux Mac.sh"
  ```
  *(You can also make them executable once with `chmod +x "Install ScanSplitter Linux Mac.sh" "Run ScanSplitter Linux Mac.sh"` and run `./"Run ScanSplitter Linux Mac.sh"` directly.)*

---

## Key Features

### 1. Drag & Drop Scanner Bed Images
- Drop scanned images (`.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`, `.bmp`, `.webp`) directly onto the application window from Windows File Explorer.
- Works with scanner beds containing multiple loose, crooked, or tilted photographs.

### 2. Intelligent Multi-Photo Detection
- **Adaptive Platen Background Estimation**: Samples border strips to determine platen background color (white, off-white, grey, or black lids).
- **Hybrid Segmentation**: Combines perceptual LAB color distance with bilateral-filtered Canny edge detection and morphological closing.
- **Rotated Rectangles & Angle Snapping**: Calculates minimum-area rotated bounding rectangles with strict 90° right angles, automatically snapping near-upright angles (within ±3°) to level 0.0° rectangles.
- **Hierarchical Overlap Suppression**: Automatically detects and discards merged multi-photo containers, ensuring distinct non-overlapping boxes for each photograph.
- **Calibrated Sensitivity (1–100)**: Adaptive Otsu baseline prevents fragmentation at low sensitivity and whole-image selection at high sensitivity. Includes a one-click `↺ 50` reset button.

### 3. Interactive Crop Box Editing
- **Rectangular vs. Skewed Resize Toggle (`📐 Lock Rectangular` / `🔓 Free Skew`)**:
  - **Lock Rectangular (Default)**: Corner handle dragging keeps all four corners at strict **90° right angles** (using the opposite corner as the fixed anchor).
  - **Free Skew (Unwarp)**: Corner handles move independently, allowing you to unwarp keystoned or distorted prints.
- **On-the-Fly `Shift` Shortcut**: Hold `Shift` while dragging any corner to temporarily invert the rectangular lock without clicking the toolbar toggle.
- **One-Click Corner Squaring (`⏹ Square Box`)**:
  - Click `⏹ Square Box` in the toolbar or `⏹ Square` on any photo card to snap any skewed quadrilateral into an exact 90° rectangle.
  - Use `⏹ Square All` to orthogonalize all detected boxes at once.
- **Handles & Controls**:
  - **4 Corner Handles**: Drag any corner to fit physical borders.
  - **4 Edge Handles**: Expand or contract width and height along the edge perpendicular.
  - **Rotation Handle**: Free-spin the crop box around its center.
  - **Whole-Box Dragging**: Move the entire box by dragging inside it.
  - **Add Box Tool (`➕ Add Box`)**: Click and drag on the scanner bed to create a new crop box manually.
  - **Delete Box (`🗑 Delete Selected` / `Del` key)**: Remove unwanted boxes.
  - **Orientation Rotation (`↻ +90°` / `↺ -90°`)**: Correct photo orientation with one click.

### 4. Magnifying Loupe View
- Live, high-precision magnifying glass widget (4x, 6x, or 8x zoom) docked in the upper-right corner of the canvas.
- Automatically focuses on the exact pixel coordinate when you hover over or drag any corner handle.
- Displays high-contrast center crosshairs, active photo label, and sub-pixel coordinates for precise alignment.

### 5. Photo Dates & EXIF Metadata
- **Individual Photo Dates**: Edit year, month, and day for each photo card in the right sidebar.
- **Batch Date Tool**: Set a date (e.g. `1985-06-15`) and click **Apply to All** to tag the entire batch at once.
- **EXIF Embedding**: Automatically writes dates to standard EXIF tags (`DateTimeOriginal`, `DateTimeDigitized`, and `DateTime`) during export.

### 6. High-Fidelity Deskewed Export
- **Perspective Deskewing**: Extracts each crop using high-order Lanczos perspective transforms at full original scanner resolution.
- **Output Formats**: Choose between JPEG (with adjustable quality 70–100%) or lossless PNG.
- **Custom Naming**: Customizable filename patterns (e.g. `{date}_{prefix}_{index:02d}.jpg`).
- **Destination Folder**: Automatically defaults to the source image's directory, with a native Windows folder browser if you prefer another location. Option to open the folder automatically upon export completion.

---

## Controls & Shortcuts Cheat Sheet

| Action | Control / Shortcut |
|---|---|
| **Zoom In / Out** | Mouse Wheel (or Trackpad Pinch) |
| **Pan Canvas** | Middle Mouse Drag, Right Click Drag, or `Space` + Left Click Drag |
| **Fit in View** | `Ctrl + 0` or "Fit in View" toolbar button |
| **Toggle Square / Skew Mode** | Toolbar button `📐 Lock Rectangular` |
| **Temporary Mode Invert** | Hold `Shift` while dragging any corner |
| **Snap Corners to 90°** | `⏹ Square Box` (Toolbar) or `⏹ Square` (Sidebar card) |
| **Square All Detected Boxes** | `⏹ Square All` button (Sidebar) |
| **Add Box Manually** | Toolbar button `➕ Add Box` then click & drag |
| **Delete Selected Box** | `Delete` or `Backspace` key |
| **Nudge Selected Box** | `Arrow Keys` (1px) / `Shift + Arrow Keys` (10px) |
| **Rotate 90° CW / CCW** | Toolbar buttons `↻ +90°` / `↺ -90°` |
| **Adjust Loupe Zoom** | Toolbar buttons `Loupe 4x`, `Loupe 6x`, `Loupe 8x` |

---

## Project Structure

```text
App1 - ScanSlicer/
├── app/
│   ├── __init__.py          # Package initialization (v1.1.0)
│   ├── detector.py          # Multi-method scanner bed crop detection & deskewing
│   ├── crop_item.py         # Interactive QGraphicsItem (rectangular lock, corners, rotation)
│   ├── canvas_view.py       # QGraphicsView with pan, zoom, drag-and-drop & loupe
│   ├── loupe_widget.py      # Magnifying loupe widget (4x, 6x, 8x crosshair zoom)
│   ├── photo_model.py       # Data model for photo crops, dates, and dimensions
│   ├── sidebar.py           # Sidebar photo cards, batch date tool, sensitivity slider
│   ├── export_dialog.py     # Output directory, format selection, and batch export
│   ├── exif_helper.py       # EXIF date embedding and metadata injection
│   ├── main.py              # Application entry point
│   └── styles.py            # Modern dark theme stylesheet
├── releases/
│   └── Compile EXE.bat                  # Standalone Windows EXE builder
├── Install ScanSplitter Windows.bat     # Windows venv + dependency installer
├── Run ScanSplitter Windows.bat         # Silent Windows launcher
├── Run ScanSplitter Windows Console.bat # Console Windows launcher
├── Install ScanSplitter Linux Mac.sh    # Linux/macOS venv + dependency installer
├── Run ScanSplitter Linux Mac.sh        # Linux/macOS launcher
├── requirements.txt                     # Core dependencies
├── CHANGELOG.md             # Version history and release notes
└── README.md                # Documentation
```

---

## Release Notes

See [CHANGELOG.md](CHANGELOG.md) for full version history and release notes.
