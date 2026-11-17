"""
Sidebar widget displaying photo thumbnails, metadata, date pickers,
orientation controls, and batch date tools.
"""

from typing import List, Optional, Callable
import cv2
import numpy as np

from PyQt6.QtCore import Qt, QDate, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QColor, QIntValidator
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QCalendarWidget, QDialog, QScrollArea, QFrame, QSlider
)

from . import get_asset_path
from .photo_model import PhotoModel
from .detector import extract_deskewed_crop


_MONTH_NAMES = [
    "01 Jan", "02 Feb", "03 Mar", "04 Apr", "05 May", "06 Jun",
    "07 Jul", "08 Aug", "09 Sep", "10 Oct", "11 Nov", "12 Dec"
]


class SmartDatePicker(QWidget):
    """Compact Year / Month / Day selector with a dark-themed calendar popup."""

    dateChanged = pyqtSignal(QDate)

    def __init__(self, initial_date: Optional[QDate] = None, parent=None):
        super().__init__(parent)
        self._updating = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        chevron_path = get_asset_path("chevron_down.svg")
        arrow_rule = (
            f"image: url({chevron_path.as_posix()}); width: 10px; height: 6px;"
            if chevron_path.exists()
            else ""
        )

        field_style = f"""
            QComboBox {{
                background-color: #2b3342;
                color: #ffffff;
                border: 1px solid #455066;
                border-radius: 4px;
                padding: 2px 4px;
                font-size: 11px;
                min-height: 20px;
            }}
            QComboBox:focus, QComboBox:on {{
                border-color: #00d2ff;
            }}
            QComboBox QLineEdit {{
                background: transparent;
                color: #ffffff;
                border: none;
                padding: 0px;
                margin: 0px;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                border: none;
                width: 14px;
            }}
            QComboBox::down-arrow {{
                {arrow_rule}
            }}
            QComboBox QAbstractItemView {{
                background-color: #1e2430;
                color: #ffffff;
                selection-background-color: #0088cc;
            }}
        """

        max_year = max(2030, QDate.currentDate().year() + 1)
        self.year_combo = QComboBox(self)
        self.year_combo.setEditable(True)
        self.year_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.year_combo.addItems([str(y) for y in range(max_year, 1899, -1)])
        self.year_combo.setMaxVisibleItems(14)
        self.year_combo.lineEdit().setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.year_combo.lineEdit().setValidator(QIntValidator(1850, 2100, self))
        self.year_combo.lineEdit().setMaxLength(4)
        self.year_combo.setFixedWidth(58)
        self.year_combo.setToolTip("Year (pick from list or type 1850–2100)")
        self.year_combo.setStyleSheet(field_style)

        self.month_combo = QComboBox(self)
        self.month_combo.addItems(_MONTH_NAMES)
        self.month_combo.setMaxVisibleItems(12)
        self.month_combo.setMinimumWidth(66)
        self.month_combo.setToolTip("Month")
        self.month_combo.setStyleSheet(field_style)

        self.day_combo = QComboBox(self)
        self.day_combo.addItems([f"{d:02d}" for d in range(1, 32)])
        self.day_combo.setMaxVisibleItems(16)
        self.day_combo.setFixedWidth(44)
        self.day_combo.setToolTip("Day")
        self.day_combo.setStyleSheet(field_style)

        self.cal_btn = QPushButton("📅", self)
        self.cal_btn.setFixedSize(24, 24)
        self.cal_btn.setToolTip("Pick from calendar")
        self.cal_btn.setStyleSheet("""
            QPushButton {
                background-color: #2b3342;
                color: #e2e8f0;
                border: 1px solid #455066;
                border-radius: 4px;
                font-size: 11px;
                padding: 0px;
            }
            QPushButton:hover {
                border-color: #00d2ff;
                background-color: #323c4d;
            }
        """)

        layout.addWidget(self.year_combo)
        layout.addWidget(self.month_combo, stretch=1)
        layout.addWidget(self.day_combo)
        layout.addWidget(self.cal_btn)

        self.setDate(initial_date if (initial_date and initial_date.isValid()) else QDate.currentDate())

        self.year_combo.currentTextChanged.connect(self._on_year_text_changed)
        self.month_combo.currentIndexChanged.connect(self._on_parts_changed)
        self.day_combo.currentIndexChanged.connect(self._on_parts_changed)
        self.cal_btn.clicked.connect(self._open_calendar_popup)

    def _parsed_year(self) -> int:
        try:
            y = int(self.year_combo.currentText())
            return max(1850, min(2100, y))
        except ValueError:
            return QDate.currentDate().year()

    def _sync_day_items(self, max_d: int, selected_day: int):
        if self.day_combo.count() != max_d:
            self.day_combo.clear()
            self.day_combo.addItems([f"{d:02d}" for d in range(1, max_d + 1)])
        clamped_d = max(1, min(max_d, selected_day))
        self.day_combo.setCurrentIndex(clamped_d - 1)

    def _on_year_text_changed(self, text: str):
        if self._updating or len(text) < 4:
            return
        self._on_parts_changed()

    def date(self) -> QDate:
        y = self._parsed_year()
        m = self.month_combo.currentIndex() + 1
        max_d = QDate(y, m, 1).daysInMonth()
        d = min(self.day_combo.currentIndex() + 1, max_d)
        return QDate(y, m, d)

    def setDate(self, qdate: QDate):
        if not qdate.isValid():
            return
        self._updating = True
        try:
            self.year_combo.setCurrentText(str(qdate.year()))
            self.month_combo.setCurrentIndex(qdate.month() - 1)
            self._sync_day_items(qdate.daysInMonth(), qdate.day())
        finally:
            self._updating = False

    def _on_parts_changed(self):
        if self._updating:
            return
        self._updating = True
        try:
            y = self._parsed_year()
            m = self.month_combo.currentIndex() + 1
            max_d = QDate(y, m, 1).daysInMonth()
            cur_d = self.day_combo.currentIndex() + 1
            self._sync_day_items(max_d, cur_d)
        finally:
            self._updating = False
        self.dateChanged.emit(self.date())

    def _open_calendar_popup(self):
        popup = QDialog(self, Qt.WindowType.Popup)
        popup.setStyleSheet("QDialog { background-color: #1a1e27; border: 1px solid #00d2ff; border-radius: 6px; }")
        vlayout = QVBoxLayout(popup)
        vlayout.setContentsMargins(6, 6, 6, 6)

        cal = QCalendarWidget(popup)
        cal.setMinimumDate(QDate(1850, 1, 1))
        cal.setMaximumDate(QDate(2100, 12, 31))
        cal.setSelectedDate(self.date())
        cal.setGridVisible(True)

        def on_picked(qdate: QDate):
            self.setDate(qdate)
            self.dateChanged.emit(qdate)
            popup.accept()

        cal.clicked.connect(on_picked)
        vlayout.addWidget(cal)

        pos = self.cal_btn.mapToGlobal(self.cal_btn.rect().bottomRight())
        popup.adjustSize()
        popup.move(pos.x() - popup.width(), pos.y() + 4)
        popup.exec()


class PhotoCardWidget(QFrame):
    """Card representing a single detected photo in the sidebar."""

    selected = pyqtSignal(int)      # photo_id
    deleted = pyqtSignal(int)       # photo_id
    date_changed = pyqtSignal(int, str)  # photo_id, date_str
    rotate_requested = pyqtSignal(int, int)  # photo_id, delta_degrees
    straighten_requested = pyqtSignal(int)  # photo_id

    def __init__(self, model: PhotoModel, source_image: Optional[np.ndarray], parent=None):
        super().__init__(parent)
        self.model = model
        self.source_image = source_image

        self.setObjectName("PhotoCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_style(False)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # Header row: Photo number, dimensions, delete button
        hdr_layout = QHBoxLayout()
        self.title_label = QLabel(f"Photo #{model.id}", self)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #00d2ff;")
        
        dim_w, dim_h = model.dimensions
        self.dim_label = QLabel(f"{dim_w}x{dim_h} px", self)
        self.dim_label.setStyleSheet("color: #8fa0b5; font-size: 11px;")

        del_btn = QPushButton("✕", self)
        del_btn.setFixedSize(22, 22)
        del_btn.setToolTip("Remove this crop box")
        del_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #ff5252;
                font-weight: bold;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: rgba(255, 82, 82, 0.2);
            }
        """)
        del_btn.clicked.connect(lambda: self.deleted.emit(self.model.id))

        hdr_layout.addWidget(self.title_label)
        hdr_layout.addWidget(self.dim_label)
        hdr_layout.addStretch()
        hdr_layout.addWidget(del_btn)
        main_layout.addLayout(hdr_layout)

        # Body row: Thumbnail preview + Rotation buttons
        body_layout = QHBoxLayout()
        self.thumb_label = QLabel(self)
        self.thumb_label.setFixedSize(90, 70)
        self.thumb_label.setStyleSheet("background-color: #12151c; border-radius: 6px; border: 1px solid #363e4f;")
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_thumbnail()

        # Rotation buttons (+90 / -90)
        rot_layout = QVBoxLayout()
        rot_layout.setSpacing(4)
        rot_ccw_btn = QPushButton("↺ 90°", self)
        rot_ccw_btn.setToolTip("Rotate 90° Counter-Clockwise")
        rot_ccw_btn.setStyleSheet("font-size: 11px; padding: 4px 8px; background-color: #2b3342; border-radius: 4px; color: #e0e6ed;")
        rot_ccw_btn.clicked.connect(lambda: self.rotate_requested.emit(self.model.id, 270))

        rot_cw_btn = QPushButton("↻ 90°", self)
        rot_cw_btn.setToolTip("Rotate 90° Clockwise")
        rot_cw_btn.setStyleSheet("font-size: 11px; padding: 4px 8px; background-color: #2b3342; border-radius: 4px; color: #e0e6ed;")
        rot_cw_btn.clicked.connect(lambda: self.rotate_requested.emit(self.model.id, 90))

        square_btn = QPushButton("⏹ Square", self)
        square_btn.setToolTip("Snap corners into an exact 90° right-angled rectangle")
        square_btn.setStyleSheet("font-size: 11px; padding: 4px 8px; background-color: #243547; border: 1px solid #00a2cc; border-radius: 4px; color: #00d2ff;")
        square_btn.clicked.connect(lambda: self.straighten_requested.emit(self.model.id))

        rot_layout.addWidget(rot_ccw_btn)
        rot_layout.addWidget(rot_cw_btn)
        rot_layout.addWidget(square_btn)

        body_layout.addWidget(self.thumb_label)
        body_layout.addLayout(rot_layout)
        body_layout.addStretch()
        main_layout.addLayout(body_layout)

        # Date input row
        date_layout = QHBoxLayout()
        date_lbl = QLabel("Date:", self)
        date_lbl.setStyleSheet("color: #a0aec0; font-size: 11px;")

        self.date_input = SmartDatePicker(parent=self)

        # Parse model date
        try:
            parts = self.model.date_str.split("-")
            qdate = QDate(int(parts[0]), int(parts[1]), int(parts[2]))
            self.date_input.setDate(qdate)
        except Exception:
            self.date_input.setDate(QDate.currentDate())

        self.date_input.dateChanged.connect(self._on_date_changed)

        date_layout.addWidget(date_lbl)
        date_layout.addWidget(self.date_input, stretch=1)
        main_layout.addLayout(date_layout)

    def update_thumbnail(self):
        """Regenerates the small thumbnail preview for this card."""
        if self.source_image is None or self.source_image.size == 0:
            return

        try:
            cropped = extract_deskewed_crop(
                self.source_image,
                self.model.corners,
                rotation_offset=self.model.rotation_offset
            )
            if cropped is not None and cropped.size > 0:
                h, w = cropped.shape[:2]
                rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
                bytes_per_line = 3 * w
                q_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                pix = QPixmap.fromImage(q_img).scaled(
                    90, 70,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.thumb_label.setPixmap(pix)
        except Exception:
            pass

    def update_style(self, selected: bool):
        if selected:
            self.setStyleSheet("""
                QFrame#PhotoCard {
                    background-color: #212936;
                    border: 2px solid #00d2ff;
                    border-radius: 8px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame#PhotoCard {
                    background-color: #1a1e27;
                    border: 1px solid #313a4a;
                    border-radius: 8px;
                }
                QFrame#PhotoCard:hover {
                    border: 1px solid #00a2cc;
                }
            """)

    def set_date_str(self, date_str: str):
        self.model.date_str = date_str
        try:
            parts = date_str.split("-")
            self.date_input.setDate(QDate(int(parts[0]), int(parts[1]), int(parts[2])))
        except Exception:
            pass

    def _on_date_changed(self, qdate: QDate):
        date_str = qdate.toString("yyyy-MM-dd")
        self.model.date_str = date_str
        self.date_changed.emit(self.model.id, date_str)

    def mousePressEvent(self, event):
        self.selected.emit(self.model.id)
        super().mousePressEvent(event)


class SidebarWidget(QWidget):
    """Sidebar containing list of detected photos, batch tools, and sensitivity slider."""

    photo_selected = pyqtSignal(int)
    photo_deleted = pyqtSignal(int)
    photo_rotated = pyqtSignal(int, int)  # photo_id, delta_degrees
    date_updated = pyqtSignal(int, str)
    batch_date_applied = pyqtSignal(str)
    redetect_requested = pyqtSignal(int)  # sensitivity
    photo_straightened = pyqtSignal(int)  # photo_id
    straighten_all_requested = pyqtSignal()
    export_requested = pyqtSignal()

    @staticmethod
    def _get_sens_text(val: int) -> str:
        if val == 50:
            return "Sensitivity: 50 (Default)"
        elif val < 40:
            return f"Sensitivity: {val} (High Contrast)"
        elif val > 65:
            return f"Sensitivity: {val} (Faint Borders)"
        else:
            return f"Sensitivity: {val}"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarWidget")
        self.setFixedWidth(310)
        self.setStyleSheet("QWidget#SidebarWidget { background-color: #161920; border-left: 1px solid #282f3d; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # 1. Detection Settings Section
        det_frame = QFrame(self)
        det_frame.setStyleSheet("background-color: #1e232d; border-radius: 8px; padding: 6px;")
        det_layout = QVBoxLayout(det_frame)
        det_layout.setSpacing(6)

        det_title = QLabel("Auto Detection", det_frame)
        det_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #e2e8f0; border: none;")

        sens_info_layout = QHBoxLayout()
        self.sens_label = QLabel(self._get_sens_text(50), det_frame)
        self.sens_label.setStyleSheet("color: #a0aec0; font-size: 11px; border: none;")

        reset_sens_btn = QPushButton("↺ 50", det_frame)
        reset_sens_btn.setFixedSize(36, 20)
        reset_sens_btn.setToolTip("Reset sensitivity back to default (50)")
        reset_sens_btn.setStyleSheet("""
            QPushButton {
                background-color: #242a36;
                color: #8fa0b5;
                font-size: 10px;
                border: 1px solid #363e4f;
                border-radius: 3px;
            }
            QPushButton:hover {
                color: #00d2ff;
                border-color: #00d2ff;
            }
        """)
        reset_sens_btn.clicked.connect(lambda: self.sens_slider.setValue(50))

        sens_info_layout.addWidget(self.sens_label, stretch=1)
        sens_info_layout.addWidget(reset_sens_btn)

        self.sens_slider = QSlider(Qt.Orientation.Horizontal, det_frame)
        self.sens_slider.setRange(1, 100)
        self.sens_slider.setValue(50)
        self.sens_slider.setToolTip(
            "Default 50 works for most scans.\n"
            "Increase (60-80) if faint photo borders are missed.\n"
            "Decrease (20-40) if background paper noise is being detected."
        )
        self.sens_slider.valueChanged.connect(lambda v: self.sens_label.setText(self._get_sens_text(v)))

        det_layout.addWidget(det_title)
        det_layout.addLayout(sens_info_layout)
        det_layout.addWidget(self.sens_slider)

        self.redetect_btn = QPushButton("🔍 Re-Detect Photos", det_frame)
        self.redetect_btn.setStyleSheet("""
            QPushButton {
                background-color: #2b3342;
                color: #00d2ff;
                font-weight: bold;
                border: 1px solid #00d2ff;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #00d2ff;
                color: #12151c;
            }
        """)
        self.redetect_btn.clicked.connect(lambda: self.redetect_requested.emit(self.sens_slider.value()))
        det_layout.addWidget(self.redetect_btn)
        layout.addWidget(det_frame)

        # 2. Batch Date Setter Section
        batch_frame = QFrame(self)
        batch_frame.setObjectName("BatchFrame")
        batch_frame.setStyleSheet("QFrame#BatchFrame { background-color: #1e232d; border-radius: 8px; }")
        batch_layout = QVBoxLayout(batch_frame)
        batch_layout.setContentsMargins(10, 10, 10, 10)
        batch_layout.setSpacing(6)

        batch_hdr_row = QHBoxLayout()
        batch_title = QLabel("Batch Date Setter", batch_frame)
        batch_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #e2e8f0; border: none;")

        apply_all_btn = QPushButton("Apply to All", batch_frame)
        apply_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #0088cc;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #00a0f0;
            }
        """)
        apply_all_btn.clicked.connect(self._on_apply_batch_date)

        batch_hdr_row.addWidget(batch_title)
        batch_hdr_row.addStretch()
        batch_hdr_row.addWidget(apply_all_btn)

        self.batch_date_edit = SmartDatePicker(QDate.currentDate(), batch_frame)

        batch_layout.addLayout(batch_hdr_row)
        batch_layout.addWidget(self.batch_date_edit)
        layout.addWidget(batch_frame)

        # 3. Photo Cards Scroll Area Header
        hdr_box = QHBoxLayout()
        self.count_label = QLabel("Detected Photos (0)", self)
        self.count_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #00d2ff;")
        
        square_all_btn = QPushButton("⏹ Square All", self)
        square_all_btn.setToolTip("Snap all detected boxes back to exact 90° right angles")
        square_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #242c38;
                color: #00d2ff;
                font-size: 11px;
                border: 1px solid #364459;
                border-radius: 4px;
                padding: 3px 8px;
            }
            QPushButton:hover {
                background-color: #00d2ff;
                color: #0f172a;
            }
        """)
        square_all_btn.clicked.connect(lambda: self.straighten_all_requested.emit())

        hdr_box.addWidget(self.count_label)
        hdr_box.addStretch()
        hdr_box.addWidget(square_all_btn)
        layout.addLayout(hdr_box)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(10)
        self.cards_layout.addStretch()
        self.scroll_area.setWidget(self.cards_container)

        layout.addWidget(self.scroll_area, stretch=1)

        # 4. Big Export Button at Bottom
        self.export_btn = QPushButton("💾 Export Cropped Photos", self)
        self.export_btn.setStyleSheet("""
            QPushButton {
                background-color: #00c853;
                color: white;
                font-size: 14px;
                font-weight: bold;
                border: none;
                border-radius: 8px;
                padding: 12px 18px;
            }
            QPushButton:hover {
                background-color: #00e676;
            }
            QPushButton:disabled {
                background-color: #313d4f;
                color: #718096;
            }
        """)
        self.export_btn.clicked.connect(lambda: self.export_requested.emit())
        layout.addWidget(self.export_btn)

        self.cards: List[PhotoCardWidget] = []

    def set_photos(self, models: List[PhotoModel], source_image: Optional[np.ndarray]):
        """Populates sidebar cards."""
        # Clear existing cards
        for card in self.cards:
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self.cards.clear()

        self.count_label.setText(f"Detected Photos ({len(models)})")
        self.export_btn.setEnabled(len(models) > 0)

        for model in models:
            card = PhotoCardWidget(model, source_image, self.cards_container)
            card.selected.connect(self.photo_selected.emit)
            card.deleted.connect(self.photo_deleted.emit)
            card.rotate_requested.connect(self.photo_rotated.emit)
            card.straighten_requested.connect(self.photo_straightened.emit)
            card.date_changed.connect(self.date_updated.emit)

            # Insert before the stretch item
            self.cards_layout.insertWidget(len(self.cards), card)
            self.cards.append(card)

    def select_card(self, photo_id: int):
        for card in self.cards:
            is_active = (card.model.id == photo_id)
            card.update_style(is_active)

    def refresh_thumbnails(self):
        for card in self.cards:
            card.update_thumbnail()
            w, h = card.model.dimensions
            card.dim_label.setText(f"{w}x{h} px")

    def _on_apply_batch_date(self):
        date_str = self.batch_date_edit.date().toString("yyyy-MM-dd")
        for card in self.cards:
            card.set_date_str(date_str)
        self.batch_date_applied.emit(date_str)

