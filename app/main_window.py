"""
Main Window for the ScanSplitter application.
Integrates Canvas, Sidebar, Loupe, Detection Engine, and Export Manager.
"""

from pathlib import Path
from typing import List, Optional
import numpy as np

from PyQt6.QtCore import Qt, QSize, QTimer, QSettings
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QPixmap
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QToolBar,
    QFileDialog, QMessageBox, QLabel, QPushButton, QStackedWidget, QComboBox,
    QSizePolicy, QSplitter
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

        # Resizable splitter between canvas and sidebar
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal, central_widget)
        self.main_splitter.setHandleWidth(5)
        self.main_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #282f3d;
            }
            QSplitter::handle:hover {
                background-color: #00d2ff;
            }
        """)
        self.main_splitter.addWidget(self.center_stack)
        self.main_splitter.addWidget(self.sidebar)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 0)
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)

        saved_sidebar_w = int(QSettings("ScanSlicer", "ScanSlicer").value("ui/sidebar_width", 320, type=int))
        saved_sidebar_w = max(280, min(720, saved_sidebar_w))
        self.main_splitter.setSizes([max(400, self.width() - saved_sidebar_w), saved_sidebar_w])
        self.main_splitter.splitterMoved.connect(self._on_splitter_moved)

        main_layout.addWidget(self.main_splitter)

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

    def _on_splitter_moved(self, pos: int, index: int):
        sizes = self.main_splitter.sizes()
        if len(sizes) >= 2:
            QSettings("ScanSlicer", "ScanSlicer").setValue("ui/sidebar_width", sizes[1])

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
        toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(toolbar)

        chevron_path = get_asset_path("chevron_down.svg")
        arrow_rule = (
            f"image: url({chevron_path.as_posix()}); width: 10px; height: 6px;"
            if chevron_path.exists()
            else ""
        )

        combo_style = f"""
            QComboBox {{
                background-color: #242a36;
                color: #f1f5f9;
                border: 1px solid #363e4f;
                border-radius: 6px;
                padding: 5px 22px 5px 10px;
                font-weight: 600;
                font-size: 12px;
            }}
            QComboBox:hover, QComboBox:on {{
                border-color: #00d2ff;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                border: none;
                background: transparent;
                width: 18px;
            }}
            QComboBox::down-arrow {{
                {arrow_rule}
            }}
            QComboBox QAbstractItemView {{
                background-color: #1e2430;
                color: #f1f5f9;
                border: 1px solid #363e4f;
                selection-background-color: #0088cc;
                outline: 0;
            }}
        """

        # --- Group 1: Image File & View ---
        self.open_action = QAction("📁 Open", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.setToolTip("Open a scanned image file (Ctrl+O)")
        self.open_action.triggered.connect(self.open_file_dialog)
        toolbar.addAction(self.open_action)

        self.close_action = QAction("✖ Close", self)
        self.close_action.setShortcut(QKeySequence("Ctrl+W"))
        self.close_action.setToolTip("Close the current image without deleting it (Ctrl+W)")
        self.close_action.setEnabled(False)
        self.close_action.triggered.connect(self.close_current_scan)
        toolbar.addAction(self.close_action)

        self.delete_scan_action = QAction("🗑 Delete", self)
        self.delete_scan_action.setToolTip("Permanently delete the current scanned image file from disk")
        self.delete_scan_action.setEnabled(False)
        self.delete_scan_action.triggered.connect(self.delete_current_scan)
        toolbar.addAction(self.delete_scan_action)
        toolbar.widgetForAction(self.delete_scan_action).setObjectName("DangerBtn")

        self.fit_view_action = QAction("🔍 Fit", self)
        self.fit_view_action.setShortcut(QKeySequence("Ctrl+0"))
        self.fit_view_action.setToolTip("Fit the scanned image into the view (Ctrl+0)")
        self.fit_view_action.setEnabled(False)
        self.fit_view_action.triggered.connect(self.canvas_view.fit_in_view)
        toolbar.addAction(self.fit_view_action)

        toolbar.addSeparator()

        # --- Group 2: Selection / Crop Boxes ---
        self.add_box_action = QAction("➕ Add Box", self)
        self.add_box_action.setCheckable(True)
        self.add_box_action.setEnabled(False)
        self.add_box_action.setToolTip("Click and drag on the image to draw a new crop box")
        self.add_box_action.triggered.connect(self._toggle_add_box)
        toolbar.addAction(self.add_box_action)
        toolbar.widgetForAction(self.add_box_action).setObjectName("SuccessBtn")

        self.del_box_action = QAction("➖ Remove Box", self)
        self.del_box_action.setShortcut(QKeySequence.StandardKey.Delete)
        self.del_box_action.setEnabled(False)
        self.del_box_action.setToolTip("Remove the currently selected crop box (Del)")
        self.del_box_action.triggered.connect(self.canvas_view.delete_selected_crop)
        toolbar.addAction(self.del_box_action)
        toolbar.widgetForAction(self.del_box_action).setObjectName("DangerBtn")

        self.rot_ccw_action = QAction("↺", self)
        self.rot_ccw_action.setEnabled(False)
        self.rot_ccw_action.setToolTip("Rotate selected photo 90° counter-clockwise")
        self.rot_ccw_action.triggered.connect(lambda: self._rotate_selected(270))
        toolbar.addAction(self.rot_ccw_action)

        self.rot_cw_action = QAction("↻", self)
        self.rot_cw_action.setEnabled(False)
        self.rot_cw_action.setToolTip("Rotate selected photo 90° clockwise")
        self.rot_cw_action.triggered.connect(lambda: self._rotate_selected(90))
        toolbar.addAction(self.rot_cw_action)

        toolbar.addSeparator()

        # --- Group 3: Box Geometry & Constraints ---
        self.aspect_ratio_combo = QComboBox(self)
        self.aspect_ratio_combo.setToolTip("Lock crop resizing to a common aspect ratio (or Free)")
        self._aspect_ratios = [
            ("Ratio: Free", None),
            ("Ratio: 4:3", 4.0 / 3.0),
            ("Ratio: 3:4", 3.0 / 4.0),
            ("Ratio: 3:2", 3.0 / 2.0),
            ("Ratio: 2:3", 2.0 / 3.0),
            ("Ratio: 5:7", 5.0 / 7.0),
            ("Ratio: 7:5", 7.0 / 5.0),
            ("Ratio: 1:1", 1.0),
            ("Ratio: 16:9", 16.0 / 9.0),
            ("Ratio: 9:16", 9.0 / 16.0),
        ]
        for label, _ in self._aspect_ratios:
            self.aspect_ratio_combo.addItem(label)
        self.aspect_ratio_combo.setStyleSheet(combo_style)
        self.aspect_ratio_combo.currentIndexChanged.connect(self._on_aspect_ratio_changed)
        toolbar.addWidget(self.aspect_ratio_combo)

        self.rect_lock_action = QAction("📐 Lock 90°", self)
        self.rect_lock_action.setCheckable(True)
        self.rect_lock_action.setChecked(True)
        self.rect_lock_action.setToolTip("Lock 90° right angles when resizing corners (hold Shift to temporarily toggle Free Skew)")
        self.rect_lock_action.triggered.connect(self._toggle_rect_lock)
        toolbar.addAction(self.rect_lock_action)

        self.square_action = QAction("⏹ Square Up", self)
        self.square_action.setEnabled(False)
        self.square_action.setToolTip("Snap the selected crop box into an exact 90° rectangle")
        self.square_action.triggered.connect(self.canvas_view.straighten_selected_crop)
        toolbar.addAction(self.square_action)

        keep_inside_default = QSettings("ScanSlicer", "ScanSlicer").value("canvas/keep_inside_image", True, type=bool)
        self.keep_inside_action = QAction("🖼 Keep Inside", self)
        self.keep_inside_action.setCheckable(True)
        self.keep_inside_action.setChecked(keep_inside_default)
        self.keep_inside_action.setToolTip(
            "Keep crop boxes inside the scanned image bounds. Uncheck to override and crop outside the image."
        )
        self.keep_inside_action.triggered.connect(self._toggle_keep_inside)
        toolbar.addAction(self.keep_inside_action)
        self.canvas_view.set_keep_inside_image(keep_inside_default)

        self.reset_action = QAction("🔄 Reset", self)
        self.reset_action.setEnabled(False)
        self.reset_action.setToolTip("Discard manual box edits and restore the original auto-detected boxes")
        self.reset_action.triggered.connect(self._reset_to_auto_crops)
        toolbar.addAction(self.reset_action)

        toolbar.addSeparator()

        spacer = QWidget(toolbar)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # --- Group 4: Loupe Zoom ---
        self.loupe_zoom_combo = QComboBox(self)
        self.loupe_zoom_combo.setToolTip("Magnifying loupe zoom level")
        for z_label in ("Loupe: 4x", "Loupe: 6x", "Loupe: 8x"):
            self.loupe_zoom_combo.addItem(z_label)
        self.loupe_zoom_combo.setStyleSheet(combo_style)
        self.loupe_zoom_combo.currentIndexChanged.connect(
            lambda idx: self.canvas_view.loupe.set_zoom((4.0, 6.0, 8.0)[idx])
        )
        toolbar.addWidget(self.loupe_zoom_combo)

    def _connect_signals(self):
        # Canvas Signals
        self.canvas_view.file_dropped.connect(self.load_image_file)
        self.canvas_view.selection_changed.connect(self._on_canvas_selection_changed)
        self.canvas_view.crops_updated.connect(self._on_canvas_crops_updated)
        self.canvas_view.add_box_mode_changed.connect(self._on_add_box_mode_changed)

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
        self.close_action.setEnabled(True)
        self.delete_scan_action.setEnabled(True)
        self.fit_view_action.setEnabled(True)
        self.add_box_action.setEnabled(True)
        self.reset_action.setEnabled(True)
        self.center_stack.setCurrentWidget(self.canvas_view)

        # Run auto detection with current sensitivity
        self._run_detection(self.sidebar.sens_slider.value())

        # Automatically fit the image comfortably within the view
        QTimer.singleShot(50, self.canvas_view.fit_in_view)

    def _run_detection(self, sensitivity: int):
        """Runs the computer vision detection engine on the loaded image."""
        if self.canvas_view.source_image is None:
            return

        try:
            self.status_bar.showMessage("Analyzing scanner bed for photos...")
            crops = detect_scanner_photos(
                self.canvas_view.source_image,
                sensitivity=sensitivity,
                edge_inset=self.sidebar.edge_trim_slider.value()
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
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status_bar.showMessage(f"Detection error: {e}")

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

    def _on_add_box_mode_changed(self, enabled: bool):
        self.add_box_action.blockSignals(True)
        self.add_box_action.setChecked(enabled)
        self.add_box_action.blockSignals(False)

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
            self.rect_lock_action.setText("📐 Lock 90°")
            self.status_bar.showMessage("Rectangular/Square Mode ON: Corners stay strictly 90° (Hold Shift while dragging for free skew).")
        else:
            self.rect_lock_action.setText("🔓 Free Skew")
            self.status_bar.showMessage("Free Skew Mode ON: Drag corners freely to unwarp skewed/keystoned scans (Hold Shift to lock 90°).")

    def _on_aspect_ratio_changed(self, idx: int):
        label, ratio = self._aspect_ratios[idx]
        self.canvas_view.set_aspect_ratio(ratio)
        if ratio is None:
            self.status_bar.showMessage("Aspect ratio lock cleared (Free).")
        else:
            self.status_bar.showMessage(f"Aspect ratio locked to {label.replace('Ratio: ', '')}.")

    def _toggle_keep_inside(self, checked: bool):
        QSettings("ScanSlicer", "ScanSlicer").setValue("canvas/keep_inside_image", checked)
        self.canvas_view.set_keep_inside_image(checked)
        if checked:
            self.status_bar.showMessage("Lock Inside Image ON: Crop boxes stay within scan edges.")
        else:
            self.status_bar.showMessage("Lock Inside Image OFF: Crop boxes can extend outside scan edges.")

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
        if dlg.exec():
            self.status_bar.showMessage(f"Exported {len(models)} photo(s) to {dlg.folder_input.text().strip()}")

    def _reset_workspace(self):
        """Clears the active scan and resets image/crop toolbar state."""
        self.canvas_view.clear_image()
        self.current_file_path = None
        self.auto_detected_models.clear()
        self.sidebar.set_photos([], None)
        self.close_action.setEnabled(False)
        self.delete_scan_action.setEnabled(False)
        self.fit_view_action.setEnabled(False)
        self.add_box_action.setEnabled(False)
        self.reset_action.setEnabled(False)
        self.center_stack.setCurrentWidget(self.drop_prompt)

    def close_current_scan(self):
        """Closes the currently loaded scan without deleting the file."""
        if not self.current_file_path and self.canvas_view.source_image is None:
            return
        self._reset_workspace()
        self.status_bar.showMessage("Closed image.")

    def delete_current_scan(self):
        """Deletes the currently loaded scanned image from disk after confirmation."""
        if not self.current_file_path:
            return

        scan_path = Path(self.current_file_path)
        reply = QMessageBox.question(
            self,
            "Delete Scanned Image",
            f"Are you sure you want to permanently delete this scanned image?\n\n{scan_path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            if scan_path.exists():
                scan_path.unlink()
        except Exception as e:
            QMessageBox.critical(self, "Delete Failed", f"Could not delete file:\n{e}")
            return

        self._reset_workspace()
        self.status_bar.showMessage(f"Deleted {scan_path.name}.")

