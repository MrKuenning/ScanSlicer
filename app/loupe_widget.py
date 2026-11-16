"""
Magnifying Loupe Widget for sub-pixel precision corner and crop adjustments.
"""

from typing import Optional
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPainter, QPixmap, QPen, QColor, QFont, QBrush
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QFrame


class LoupeWidget(QFrame):
    """
    A high-precision magnifying glass widget that displays an enlarged view
    of the image region around the currently manipulated handle or cursor.
    """

    def __init__(self, parent=None, size: int = 220, zoom: float = 4.0):
        super().__init__(parent)
        self.loupe_size = size
        self.zoom = zoom
        self.source_pixmap: Optional[QPixmap] = None
        self.focus_point: Optional[QPointF] = None
        self.handle_label: str = "Loupe View"

        self.setFixedSize(self.loupe_size, self.loupe_size + 36)
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(24, 28, 36, 0.95);
                border: 2px solid #00d2ff;
                border-radius: 12px;
            }
        """)

        # Label for coordinate readout
        self.info_label = QLabel("Hover over a corner", self)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet("""
            QLabel {
                color: #e0e6ed;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
                font-weight: bold;
                background: transparent;
                border: none;
                padding-top: 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addStretch()
        layout.addWidget(self.info_label)

    def set_source_pixmap(self, pixmap: Optional[QPixmap]):
        """Sets the source high-resolution pixmap."""
        self.source_pixmap = pixmap
        self.update()

    def set_focus(self, point: Optional[QPointF], label: str = "Corner"):
        """
        Updates the focus point in image coordinates (pixels).
        """
        self.focus_point = point
        self.handle_label = label

        if point is not None:
            self.info_label.setText(f"{label}\nX: {int(point.x())}, Y: {int(point.y())} ({int(self.zoom)}x)")
        else:
            self.info_label.setText("Hover handle to magnify")
        self.update()

    def set_zoom(self, zoom: float):
        self.zoom = zoom
        if self.focus_point:
            self.set_focus(self.focus_point, self.handle_label)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)  # Pixelated for crisp alignment

        # Viewport rect for the zoomed image
        margin = 8
        view_w = self.width() - (margin * 2)
        view_h = self.height() - 40 - margin
        view_rect = QRectF(margin, margin, view_w, view_h)

        # Background grid / empty area
        painter.fillRect(view_rect, QColor(35, 39, 47))

        if self.source_pixmap and not self.source_pixmap.isNull() and self.focus_point is not None:
            fx = self.focus_point.x()
            fy = self.focus_point.y()

            # Source region to crop from the original image
            src_w = view_w / self.zoom
            src_h = view_h / self.zoom
            src_x = fx - (src_w / 2.0)
            src_y = fy - (src_h / 2.0)
            src_rect = QRectF(src_x, src_y, src_w, src_h)

            painter.setClipRect(view_rect)
            painter.drawPixmap(view_rect, self.source_pixmap, src_rect)

            # Draw precise crosshairs in center of view
            cx = view_rect.center().x()
            cy = view_rect.center().y()

            # Black shadow crosshair for contrast against bright scans
            shadow_pen = QPen(QColor(0, 0, 0, 200), 3)
            painter.setPen(shadow_pen)
            painter.drawLine(int(cx - 16), int(cy), int(cx - 4), int(cy))
            painter.drawLine(int(cx + 4), int(cy), int(cx + 16), int(cy))
            painter.drawLine(int(cx), int(cy - 16), int(cx), int(cy - 4))
            painter.drawLine(int(cx), int(cy + 4), int(cx), int(cy + 16))

            # Cyan high-visibility crosshair
            cross_pen = QPen(QColor(0, 230, 255), 1.5)
            painter.setPen(cross_pen)
            painter.drawLine(int(cx - 16), int(cy), int(cx - 4), int(cy))
            painter.drawLine(int(cx + 4), int(cy), int(cx + 16), int(cy))
            painter.drawLine(int(cx), int(cy - 16), int(cx), int(cy - 4))
            painter.drawLine(int(cx), int(cy + 4), int(cx), int(cy + 16))

            # Small center target dot
            painter.setBrush(QBrush(QColor(255, 60, 60)))
            painter.setPen(QPen(QColor(255, 255, 255), 1))
            painter.drawEllipse(QPointF(cx, cy), 2.5, 2.5)

            painter.setClipping(False)

        # Draw frame around zoomed view
        painter.setPen(QPen(QColor(60, 70, 85), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(view_rect, 6, 6)

