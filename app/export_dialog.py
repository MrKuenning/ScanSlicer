"""
Export Dialog and Batch Output Processor.
Deskews each detected crop, embeds EXIF dates, and saves to PC.
"""

import os
from pathlib import Path
from typing import List, Optional
import numpy as np

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QSlider, QCheckBox, QFileDialog, QProgressBar, QMessageBox,
    QFrame
)

from .photo_model import PhotoModel
from .detector import extract_deskewed_crop
from .exif_helper import save_image_with_metadata


class ExportDialog(QDialog):
    """
    Modal or docked export dialog providing output directory selection,
    naming format, quality settings, and one-click batch export.
    """

    def __init__(
        self,
        parent,
        source_image: np.ndarray,
        crops: List[PhotoModel],
        source_filename: str = "Scan",
        default_export_dir: Optional[str] = None
    ):
        super().__init__(parent)
        self.source_image = source_image
        self.crops = crops
        self.source_filename = Path(source_filename).stem if source_filename else "Scan"
        self.default_export_dir = default_export_dir

        self.setWindowTitle("Export Cropped Photos")
        self.setMinimumWidth(500)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e222b;
                color: #e0e6ed;
            }
            QLabel {
                color: #cfd7e3;
                font-size: 13px;
            }
            QLineEdit, QComboBox {
                background-color: #2b313d;
                color: #ffffff;
                border: 1px solid #454f63;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QPushButton {
                background-color: #0088cc;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #00a0f0;
            }
            QCheckBox {
                color: #e0e6ed;
                font-size: 13px;
            }
            QProgressBar {
                background-color: #2b313d;
                border: 1px solid #454f63;
                border-radius: 6px;
                text-align: center;
                color: white;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #00d2ff;
                border-radius: 5px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        # Title
        title = QLabel(f"Export {len(crops)} Cropped Photo(s)", self)
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #00d2ff;")
        layout.addWidget(title)

        # 1. Output Folder Selection
        folder_layout = QHBoxLayout()
        self.folder_input = QLineEdit(self)
        if self.default_export_dir and Path(self.default_export_dir).exists():
            default_dir = str(Path(self.default_export_dir).resolve())
        else:
            default_dir = str(Path.home() / "Pictures" / "ScanSplitter_Output")
        self.folder_input.setText(default_dir)
        browse_btn = QPushButton("Browse...", self)
        browse_btn.clicked.connect(self._browse_folder)
        folder_layout.addWidget(self.folder_input, stretch=1)
        folder_layout.addWidget(browse_btn)

        layout.addWidget(QLabel("Output Folder:", self))
        layout.addLayout(folder_layout)

        # 2. File Format & Quality
        fmt_layout = QHBoxLayout()
        self.format_combo = QComboBox(self)
        self.format_combo.addItems(["JPEG (.jpg) - High Quality", "PNG (.png) - Lossless"])
        self.format_combo.currentIndexChanged.connect(self._toggle_quality)

        self.quality_label = QLabel("Quality: 95%", self)
        self.quality_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.quality_slider.setRange(70, 100)
        self.quality_slider.setValue(95)
        self.quality_slider.valueChanged.connect(lambda v: self.quality_label.setText(f"Quality: {v}%"))

        fmt_layout.addWidget(self.format_combo, stretch=1)
        fmt_layout.addWidget(self.quality_label)
        fmt_layout.addWidget(self.quality_slider, stretch=1)

        layout.addWidget(QLabel("Image Format:", self))
        layout.addLayout(fmt_layout)

        # 3. Filename Pattern
        name_layout = QHBoxLayout()
        self.name_prefix = QLineEdit(self)
        self.name_prefix.setText(f"{self.source_filename}")
        self.name_pattern = QComboBox(self)
        self.name_pattern.addItems([
            "{prefix}_{index:02d}_{date}",
            "{date}_{prefix}_{index:02d}",
            "{prefix}_Photo_{index:02d}",
            "Photo_{index:02d}_{date}"
        ])
        name_layout.addWidget(self.name_prefix, stretch=1)
        name_layout.addWidget(self.name_pattern, stretch=1)

        layout.addWidget(QLabel("Filename Pattern:", self))
        layout.addLayout(name_layout)

        # 4. Checkboxes
        self.embed_exif_check = QCheckBox("Embed date and metadata into photo EXIF", self)
        self.embed_exif_check.setChecked(True)
        layout.addWidget(self.embed_exif_check)

        settings = QSettings("ScanSlicer", "ScanSlicer")
        open_folder_default = settings.value("export/open_output_folder", True, type=bool)

        self.open_folder_check = QCheckBox("Open output folder when finished", self)
        self.open_folder_check.setChecked(open_folder_default)
        self.open_folder_check.toggled.connect(self._on_open_folder_toggled)
        layout.addWidget(self.open_folder_check)

        skip_confirm_default = settings.value("export/skip_confirmation", False, type=bool)
        self.skip_confirm_check = QCheckBox("Disable confirmation dialog after exporting", self)
        self.skip_confirm_check.setChecked(skip_confirm_default)
        self.skip_confirm_check.toggled.connect(self._on_skip_confirm_toggled)
        layout.addWidget(self.skip_confirm_check)

        # Progress bar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Action Buttons
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.setStyleSheet("background-color: #454f63;")
        cancel_btn.clicked.connect(self.reject)

        self.export_btn = QPushButton(f"Export {len(crops)} Photos", self)
        self.export_btn.setStyleSheet("background-color: #00c853; font-size: 14px; padding: 10px 20px;")
        self.export_btn.clicked.connect(self._run_export)

        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(self.export_btn)
        layout.addLayout(btn_layout)

    def _on_open_folder_toggled(self, checked: bool):
        QSettings("ScanSlicer", "ScanSlicer").setValue("export/open_output_folder", checked)

    def _on_skip_confirm_toggled(self, checked: bool):
        QSettings("ScanSlicer", "ScanSlicer").setValue("export/skip_confirmation", checked)

    def _toggle_quality(self, idx):
        is_jpeg = (idx == 0)
        self.quality_label.setEnabled(is_jpeg)
        self.quality_slider.setEnabled(is_jpeg)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Directory", self.folder_input.text())
        if folder:
            self.folder_input.setText(folder)

    def _run_export(self):
        out_dir = Path(self.folder_input.text().strip())
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create output directory:\n{e}")
            return

        is_jpeg = (self.format_combo.currentIndex() == 0)
        ext = ".jpg" if is_jpeg else ".png"
        quality = self.quality_slider.value()
        pattern = self.name_pattern.currentText()
        prefix = self.name_prefix.text().strip() or "Photo"

        self.progress_bar.setMaximum(len(self.crops))
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.export_btn.setEnabled(False)

        saved_count = 0
        for idx, model in enumerate(self.crops, start=1):
            date_val = model.date_str or "undated"
            file_name = pattern.format(prefix=prefix, index=idx, date=date_val) + ext
            file_path = out_dir / file_name

            # 1. Deskew & extract crop using perspective transform
            cropped = extract_deskewed_crop(
                self.source_image,
                model.corners,
                rotation_offset=model.rotation_offset
            )

            # 2. Save with EXIF metadata
            embed_date = model.date_str if self.embed_exif_check.isChecked() else None
            success = save_image_with_metadata(
                cropped,
                file_path,
                date_str=embed_date,
                quality=quality
            )
            if success:
                saved_count += 1

            self.progress_bar.setValue(idx)

        # Finished
        if self.open_folder_check.isChecked() and out_dir.exists():
            try:
                os.startfile(str(out_dir))
            except Exception:
                pass

        if not self.skip_confirm_check.isChecked():
            QMessageBox.information(
                self,
                "Export Complete",
                f"Successfully saved {saved_count} cropped photo(s) to:\n{out_dir}"
            )
        self.accept()

