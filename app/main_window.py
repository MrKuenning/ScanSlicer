"""
Main Window for the ScanSplitter application.
Integrates Canvas, Sidebar, Loupe, Detection Engine, and Export Manager.
"""

from pathlib import Path
from typing import List, Optional
import numpy as np

from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QPixmap
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QToolBar,
    QFileDialog, QMessageBox, QLabel, QPushButton, QStackedWidget
)

from .photo_model import PhotoModel
from .detector import detect_scanner_photos
from .canvas_view import CanvasView
from .sidebar import SidebarWidget
from .export_dialog import ExportDialog
from .styles import DARK_THEME_QSS
from . import __version__, get_asset_path


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"ScanSplitter v{__version__} - Auto Scanner Bed Photo Cropper")
        self.resize(1350, 850)
        self.setStyleSheet(DARK_THEME_QSS)

        # Set Window Icon
        icon_ico = get_asset_path("icon.ico")
        icon_png = get_asset_path("icon.png")
        icon_path = icon_ico if icon_ico.exists() else icon_png
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.current_file_path: Optional[str] = None
        self.auto_detected_models: List[PhotoModel] = []

        # Central Widget & Layout
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Center area: Stack containing Drop Prompt and Canvas View
        self.center_stack = QStackedWidget(self)
        self.drop_prompt = self._create_drop_prompt()
        self.canvas_view = CanvasView(self)

        self.center_stack.addWidget(self.drop_prompt)
        self.center_stack.addWidget(self.canvas_view)
        self.center_stack.setCurrentWidget(self.drop_prompt)

        # Right Sidebar
        self.sidebar = SidebarWidget(self)

        main_layout.addWidget(self.center_stack, stretch=1)
        main_layout.addWidget(self.sidebar)

        # Setup Toolbar & Status Bar
        self._create_toolbar()
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Ready. Drop a scanned image to begin.")

        # Connect Signals
        self._connect_signals()

    def _create_drop_prompt(self) -> QWidget:
        """Friendly welcome screen when no image is loaded yet."""
        prompt = QWidget(self)
        prompt.setAcceptDrops(True)
        layout = QVBoxLayout(prompt)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        icon_label = QLabel(prompt)
        icon_png = get_asset_path("icon.png")
        if icon_png.exists():
            pixmap = QPixmap(str(icon_png)).scaled(
                128, 128, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            icon_label.setPixmap(pixmap)
        else:
            icon_label.setText("📷")
            icon_label.setStyleSheet("font-size: 64px;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Drop Scanner Bed Image Here", prompt)
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #00d2ff;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Supports scanned pages with multiple crooked photos (JPG, PNG, TIFF, BMP)", prompt)
        subtitle.setStyleSheet("font-size: 13px; color: #94a3b8;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        open_btn = QPushButton("📁 Browse Image File...", prompt)
        open_btn.setStyleSheet("""
            QPushButton {
                background-color: #0088cc;
                color: white;
                font-size: 14px;
                font-weight: bold;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
            }
            QPushButton:hover {
                background-color: #00a0f0;
            }
        """)
        open_btn.clicked.connect(self.open_file_dialog)

        layout.addWidget(icon_label)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(open_btn)

        # Enable drop on prompt widget
        prompt.dragEnterEvent = lambda e: e.acceptProposedAction() if e.mimeData().hasUrls() else None
        prompt.dropEvent = self._on_prompt_drop

        return prompt

    def _on_prompt_drop(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if Path(path).suffix.lower() in (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"):
                    self.load_image_file(path)
                    event.acceptProposedAction()
                    return

    def _create_toolbar(self):
        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        # Open File Action
        self.open_action = QAction("📁 Open Image", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.open_file_dialog)
        toolbar.addAction(self.open_action)

        toolbar.addSeparator()

        # Add Crop Box Tool
        self.add_box_action = QAction("➕ Add Box", self)
        self.add_box_action.setCheckable(True)
        self.add_box_action.setToolTip("Click and drag on the image to create a new crop box manually")
        self.add_box_action.triggered.connect(self._toggle_add_box)
        toolbar.addAction(self.add_box_action)

        # Delete Selected Crop Box
        self.del_box_action = QAction("🗑 Delete Selected", self)
        self.del_box_action.setShortcut(QKeySequence.StandardKey.Delete)
        self.del_box_action.setToolTip("Delete the currently selected crop box (Del)")
        self.del_box_action.triggered.connect(self.canvas_view.delete_selected_crop)
        toolbar.addAction(self.del_box_action)

        toolbar.addSeparator()

        # Orientation Rotations
        self.rot_ccw_action = QAction("↺ Rotate -90°", self)
        self.rot_ccw_action.setToolTip("Rotate selected photo counter-clockwise")
        self.rot_ccw_action.triggered.connect(lambda: self._rotate_selected(270))
        toolbar.addAction(self.rot_ccw_action)

        self.rot_cw_action = QAction("↻ Rotate +90°", self)
        self.rot_cw_action.setToolTip("Rotate selected photo clockwise")
        self.rot_cw_action.triggered.connect(lambda: self._rotate_selected(90))
        toolbar.addAction(self.rot_cw_action)

        toolbar.addSeparator()

        # Mode Toggle: Rectangular (Square) vs Free Skew
        self.rect_lock_action = QAction("📐 Lock Rectangular", self)
        self.rect_lock_action.setCheckable(True)
        self.rect_lock_action.setChecked(True)
        self.rect_lock_action.setToolTip("Lock 90° right angles when resizing corners. Click to toggle Free Skew (or hold Shift while dragging).")
        self.rect_lock_action.triggered.connect(self._toggle_rect_lock)
        toolbar.addAction(self.rect_lock_action)

        # Straighten / Square Box Action
        self.square_action = QAction("⏹ Square Box", self)
        self.square_action.setToolTip("Snap the selected crop box into an exact 90° rectangle (aligned with its angle)")
        self.square_action.triggered.connect(self.canvas_view.straighten_selected_crop)
        toolbar.addAction(self.square_action)

        toolbar.addSeparator()

        # Fit to Window View
        self.fit_view_action = QAction("🔍 Fit in View", self)
        self.fit_view_action.setShortcut(QKeySequence("Ctrl+0"))
        self.fit_view_action.triggered.connect(self.canvas_view.fit_in_view)
        toolbar.addAction(self.fit_view_action)

        # Reset Boxes Action
        self.reset_action = QAction("🔄 Reset Crops", self)
        self.reset_action.setToolTip("Restore initial auto-detected crop boxes")
        self.reset_action.triggered.connect(self._reset_to_auto_crops)
        toolbar.addAction(self.reset_action)

        toolbar.addSeparator()

        # Loupe Zoom controls
        zoom_4x = QAction("Loupe 4x", self)
        zoom_4x.triggered.connect(lambda: self.canvas_view.loupe.set_zoom(4.0))
        toolbar.addAction(zoom_4x)

        zoom_6x = QAction("Loupe 6x", self)
        zoom_6x.triggered.connect(lambda: self.canvas_view.loupe.set_zoom(6.0))
        toolbar.addAction(zoom_6x)

        zoom_8x = QAction("Loupe 8x", self)
        zoom_8x.triggered.connect(lambda: self.canvas_view.loupe.set_zoom(8.0))
        toolbar.addAction(zoom_8x)

    def _connect_signals(self):
        # Canvas Signals
        self.canvas_view.file_dropped.connect(self.load_image_file)
        self.canvas_view.selection_changed.connect(self._on_canvas_selection_changed)
        self.canvas_view.crops_updated.connect(self._on_canvas_crops_updated)

        # Sidebar Signals
        self.sidebar.photo_selected.connect(self.canvas_view.select_crop_by_id)
        self.sidebar.photo_deleted.connect(lambda _: self.canvas_view.delete_selected_crop())
        self.sidebar.photo_rotated.connect(self._on_sidebar_photo_rotated)
        self.sidebar.photo_straightened.connect(self.canvas_view.straighten_crop_by_id)
        self.sidebar.straighten_all_requested.connect(self.canvas_view.straighten_all_crops)
        self.sidebar.date_updated.connect(self._on_photo_date_updated)
        self.sidebar.batch_date_applied.connect(self._on_batch_date_applied)
        self.sidebar.redetect_requested.connect(self._run_detection)
        self.sidebar.export_requested.connect(self.show_export_dialog)

    def open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Scanned Image",
            "",
            "Image Files (*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp);;All Files (*.*)"
        )
        if path:
            self.load_image_file(path)

    def load_image_file(self, file_path: str):
        """Loads and processes the chosen scanned file."""
        self.status_bar.showMessage(f"Loading {Path(file_path).name}...")
        success = self.canvas_view.load_image(file_path)
        if not success:
            QMessageBox.critical(self, "Error", f"Could not load image:\n{file_path}")
            return

        self.current_file_path = file_path
        self.center_stack.setCurrentWidget(self.canvas_view)

        # Run auto detection with current sensitivity
        self._run_detection(self.sidebar.sens_slider.value())

        # Automatically fit the image comfortably within the view
        QTimer.singleShot(50, self.canvas_view.fit_in_view)

    def _run_detection(self, sensitivity: int):
        """Runs the computer vision detection engine on the loaded image."""
        if self.canvas_view.source_image is None:
            return

        self.status_bar.showMessage("Analyzing scanner bed for photos...")
        crops = detect_scanner_photos(
            self.canvas_view.source_image,
            sensitivity=sensitivity
        )

        # Convert to PhotoModel
        models: List[PhotoModel] = []
        batch_date = self.sidebar.batch_date_edit.date().toString("yyyy-MM-dd")
        for c in crops:
            models.append(PhotoModel(
                id=c.id,
                corners=c.corners,
                angle=c.angle,
                date_str=batch_date
            ))

        self.auto_detected_models = [
            PhotoModel(id=m.id, corners=m.corners.copy(), angle=m.angle, date_str=m.date_str)
            for m in models
        ]

        # Populate canvas and sidebar
        self.canvas_view.set_crops(models)
        self.sidebar.set_photos(models, self.canvas_view.source_image)

        file_name = Path(self.current_file_path).name if self.current_file_path else "Image"
        h, w = self.canvas_view.source_image.shape[:2]
        self.status_bar.showMessage(
            f"{file_name} ({w}x{h} px) - Detected {len(models)} photo(s)."
        )

    def _reset_to_auto_crops(self):
        if not self.auto_detected_models:
            return
        restored = [
            PhotoModel(id=m.id, corners=m.corners.copy(), angle=m.angle, date_str=m.date_str)
            for m in self.auto_detected_models
        ]
        self.canvas_view.set_crops(restored)
        self.sidebar.set_photos(restored, self.canvas_view.source_image)
        self.status_bar.showMessage("Restored auto-detected crops.")

    def _toggle_add_box(self, enabled: bool):
        self.canvas_view.set_add_box_mode(enabled)
        if enabled:
            self.status_bar.showMessage("Click and drag on the scanner bed to draw a new crop box.")
        else:
            self.status_bar.showMessage("Add Box mode cancelled.")

    def _rotate_selected(self, delta_degrees: int):
        sel = self.canvas_view.get_selected_crop()
        if sel:
            sel.model.rotation_offset = (sel.model.rotation_offset + delta_degrees) % 360
            sel.update()
            self.sidebar.refresh_thumbnails()

    def _on_sidebar_photo_rotated(self, photo_id: int, delta_degrees: int):
        for item in self.canvas_view.crop_items:
            if item.model.id == photo_id:
                item.model.rotation_offset = (item.model.rotation_offset + delta_degrees) % 360
                item.update()
                self.sidebar.refresh_thumbnails()
                break

    def _toggle_rect_lock(self, checked: bool):
        self.canvas_view.set_lock_rectangular(checked)
        if checked:
            self.rect_lock_action.setText("📐 Lock Rectangular")
            self.status_bar.showMessage("Rectangular/Square Mode ON: Corners stay strictly 90° (Hold Shift while dragging for free skew).")
        else:
            self.rect_lock_action.setText("🔓 Free Skew (Unwarp)")
            self.status_bar.showMessage("Free Skew Mode ON: Drag corners freely to unwarp skewed/keystoned scans (Hold Shift to lock 90°).")

    def _on_canvas_selection_changed(self, item):
        if item:
            self.sidebar.select_card(item.model.id)
            self.del_box_action.setEnabled(True)
            self.rot_cw_action.setEnabled(True)
            self.rot_ccw_action.setEnabled(True)
            self.square_action.setEnabled(True)
            w, h = item.model.dimensions
            self.status_bar.showMessage(f"Selected Photo #{item.model.id} ({w}x{h} px, Angle: {item.model.angle:.1f}°)")
        else:
            self.del_box_action.setEnabled(False)
            self.rot_cw_action.setEnabled(False)
            self.rot_ccw_action.setEnabled(False)
            self.square_action.setEnabled(False)

    def _on_canvas_crops_updated(self):
        # Synchronize models with sidebar
        models = [item.model for item in self.canvas_view.crop_items]
        self.sidebar.set_photos(models, self.canvas_view.source_image)
        sel = self.canvas_view.get_selected_crop()
        if sel:
            self.sidebar.select_card(sel.model.id)

    def _on_photo_date_updated(self, photo_id: int, date_str: str):
        for item in self.canvas_view.crop_items:
            if item.model.id == photo_id:
                item.model.date_str = date_str
                item.update()
                break

    def _on_batch_date_applied(self, date_str: str):
        for item in self.canvas_view.crop_items:
            item.model.date_str = date_str
            item.update()
        self.status_bar.showMessage(f"Applied date '{date_str}' to all photos.")

    def show_export_dialog(self):
        if not self.canvas_view.crop_items or self.canvas_view.source_image is None:
            QMessageBox.warning(self, "No Photos", "No photos have been detected or added to export.")
            return

        models = [item.model for item in self.canvas_view.crop_items]
        source_dir = str(Path(self.current_file_path).parent) if self.current_file_path else None
        dlg = ExportDialog(
            self,
            source_image=self.canvas_view.source_image,
            crops=models,
            source_filename=Path(self.current_file_path).stem if self.current_file_path else "Scan",
            default_export_dir=source_dir
        )
        dlg.exec()

