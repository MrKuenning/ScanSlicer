"""
Interactive Canvas View for viewing scanned images and adjusting crop boxes.
Supports drag-and-drop file loading, pan, zoom, manual box creation, and integrated Loupe.
"""

from typing import Optional, List, Callable
from pathlib import Path
import cv2
import numpy as np

from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QPixmap, QImage, QColor, QPen, QBrush, QCursor, QWheelEvent,
    QMouseEvent, QKeyEvent, QDragEnterEvent, QDropEvent
)
from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem,
    QWidget
)

from .photo_model import PhotoModel
from .crop_item import CropBoxItem
from .loupe_widget import LoupeWidget


class CanvasView(QGraphicsView):
    """
    QGraphicsView with smooth navigation, drag & drop, manual crop drawing,
    and a live high-precision loupe overlay.
    """

    file_dropped = pyqtSignal(str)          # Emitted when an image file is dropped
    selection_changed = pyqtSignal(object)  # Emitted when selected CropBoxItem changes
    crops_updated = pyqtSignal()            # Emitted when any crop box changes or is deleted
    add_box_mode_changed = pyqtSignal(bool) # Emitted when manual add-box mode is toggled

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
        self.setScene(self.scene)

        self.pixmap_item: Optional[QGraphicsPixmapItem] = None
        self.source_image: Optional[np.ndarray] = None  # Full resolution BGR
        self.crop_items: List[CropBoxItem] = []

        # Modes
        self.is_panning = False
        self.space_pressed = False
        self.pan_start_pos = QPointF()
        self.add_box_mode = False
        self.lock_rectangular = True
        self.aspect_ratio: Optional[float] = None
        self.keep_inside_image = True
        self.add_box_start = QPointF()
        self.temp_draw_rect: Optional[QGraphicsRectItem] = None

        # Settings
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAcceptDrops(True)
        self.setBackgroundBrush(QBrush(QColor(24, 28, 35)))

        # Embedded Loupe Widget (docked top-right in viewport)
        self.loupe = LoupeWidget(self, size=210, zoom=4.5)
        self.loupe.move(20, 20)
        self.loupe.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Position loupe at top-right with margin
        margin = 18
        self.loupe.move(self.viewport().width() - self.loupe.width() - margin, margin)

    def load_image(self, file_path: str | Path) -> bool:
        """Loads a scanned image file and displays it."""
        path = Path(file_path)
        if not path.exists():
            return False

        # Load with OpenCV for full depth support
        img = cv2.imread(str(path))
        if img is None:
            return False

        self.source_image = img
        h, w = img.shape[:2]

        # Convert to QPixmap
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        bytes_per_line = 3 * w
        q_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(q_img)

        # Clear existing scene
        self.scene.clear()
        self.crop_items.clear()

        # Add image to scene
        self.pixmap_item = self.scene.addPixmap(pixmap)
        self.pixmap_item.setZValue(0)
        self._update_padded_scene_rect()

        # Update loupe
        self.loupe.set_source_pixmap(pixmap)
        self.loupe.set_focus(None)

        # Fit image in view initially
        self.fit_in_view()
        return True

    def clear_image(self):
        """Clears the currently loaded scanned image and all crop items."""
        self.scene.clear()
        self.crop_items.clear()
        self.pixmap_item = None
        self.source_image = None
        self.loupe.set_focus(None)
        self.set_add_box_mode(False)
        self.selection_changed.emit(None)

    def _update_padded_scene_rect(self):
        """Expands the scene rect around the image so users can pan past image edges."""
        if not self.pixmap_item:
            return
        img_rect = self.pixmap_item.boundingRect()
        pad = max(img_rect.width(), img_rect.height()) * 0.6
        self.scene.setSceneRect(img_rect.adjusted(-pad, -pad, pad, pad))

    def _refresh_crop_handle_scales(self):
        """Updates crop item geometry bounds when the view zoom changes."""
        for item in self.crop_items:
            item.prepareGeometryChange()
            item.update()

    def fit_in_view(self):
        """Fits the scanned image comfortably within the canvas view."""
        if self.pixmap_item:
            self._update_padded_scene_rect()
            self.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
            self._refresh_crop_handle_scales()

    def _image_bounds(self) -> Optional[tuple[float, float]]:
        if self.pixmap_item is None:
            return None
        r = self.pixmap_item.boundingRect()
        return (float(r.width()), float(r.height()))

    def _configure_crop_item(self, item: CropBoxItem):
        item.image_bounds = self._image_bounds()
        item.keep_inside_image = self.keep_inside_image
        item.aspect_ratio = self.aspect_ratio
        item.set_lock_rectangular(self.lock_rectangular)
        item.signals.changed.connect(self._on_crop_changed)
        item.signals.selected.connect(self._on_crop_selected)
        item.signals.handle_hover.connect(self._on_handle_hover)
        item.signals.handle_drag.connect(self._on_handle_hover)

    def set_crops(self, models: List[PhotoModel]):
        """Populates the canvas with interactive crop boxes from PhotoModel items."""
        # Clear selection and detach existing crop items safely
        self.scene.clearSelection()
        for item in self.crop_items:
            item.signals.blockSignals(True)
            self.scene.removeItem(item)
        self.crop_items.clear()

        for model in models:
            item = CropBoxItem(model)
            self._configure_crop_item(item)
            self.scene.addItem(item)
            self.crop_items.append(item)

        if self.crop_items:
            self.crop_items[0].setSelected(True)
            self.selection_changed.emit(self.crop_items[0])

    def add_manual_crop(self, corners: np.ndarray, date_str: str = ""):
        """Adds a manually drawn crop box."""
        next_id = len(self.crop_items) + 1
        model = PhotoModel(id=next_id, corners=corners, date_str=date_str, lock_rectangular=self.lock_rectangular)
        item = CropBoxItem(model)
        self._configure_crop_item(item)
        self.scene.addItem(item)
        self.crop_items.append(item)

        # Select the newly added box
        for c in self.crop_items:
            c.setSelected(False)
        item.setSelected(True)
        self.selection_changed.emit(item)
        self.crops_updated.emit()

    def delete_selected_crop(self):
        """Deletes currently selected crop box."""
        selected = self.get_selected_crop()
        if selected:
            self.scene.removeItem(selected)
            self.crop_items.remove(selected)
            # Re-index remaining
            for idx, item in enumerate(self.crop_items, start=1):
                item.model.id = idx
                item.update_geometry()
            self.crops_updated.emit()
            if self.crop_items:
                self.crop_items[0].setSelected(True)
                self.selection_changed.emit(self.crop_items[0])
            else:
                self.selection_changed.emit(None)

    def get_selected_crop(self) -> Optional[CropBoxItem]:
        for item in self.crop_items:
            if item.isSelected():
                return item
        return None

    def select_crop_by_id(self, crop_id: int):
        for item in self.crop_items:
            if item.model.id == crop_id:
                item.setSelected(True)
                self.selection_changed.emit(item)
                # Pan view slightly to center crop if offscreen
                self.centerOn(item.get_center())
            else:
                item.setSelected(False)

    def set_add_box_mode(self, enabled: bool):
        """Toggles manual click-and-drag box creation."""
        self.add_box_mode = enabled
        if enabled:
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self.add_box_mode_changed.emit(enabled)

    def set_lock_rectangular(self, lock: bool):
        """Sets whether corner resizing preserves strict 90-degree right angles."""
        self.lock_rectangular = lock
        for item in self.crop_items:
            item.set_lock_rectangular(lock)

    def set_aspect_ratio(self, ratio: Optional[float]):
        """Locks or unlocks the aspect ratio (width/height) on all crop boxes."""
        self.aspect_ratio = ratio
        selected = self.get_selected_crop()
        for item in self.crop_items:
            item.set_aspect_ratio(ratio, snap_now=(item is selected))
        if selected and ratio is not None:
            self.crops_updated.emit()

    def set_keep_inside_image(self, enabled: bool):
        """Sets whether crop boxes are constrained inside the scanned image bounds."""
        self.keep_inside_image = enabled
        for item in self.crop_items:
            item.keep_inside_image = enabled

    def straighten_selected_crop(self):
        """Snaps the currently selected box into an exact 90-degree rectangle."""
        sel = self.get_selected_crop()
        if sel:
            sel.straighten()
            self.crops_updated.emit()

    def straighten_crop_by_id(self, crop_id: int):
        """Snaps a specific crop box into an exact 90-degree rectangle."""
        for item in self.crop_items:
            if item.model.id == crop_id:
                item.straighten()
                self.crops_updated.emit()
                break

    def straighten_all_crops(self):
        """Snaps all crop boxes into exact 90-degree rectangles."""
        for item in self.crop_items:
            item.straighten()
        self.crops_updated.emit()

    # --- Mouse & Keyboard Event Handlers ---

    def wheelEvent(self, event: QWheelEvent):
        """Smooth zooming with mouse wheel centered at cursor."""
        zoom_in_factor = 1.15
        zoom_out_factor = 1.0 / zoom_in_factor

        if event.angleDelta().y() > 0:
            self.scale(zoom_in_factor, zoom_in_factor)
        else:
            self.scale(zoom_out_factor, zoom_out_factor)
        self._refresh_crop_handle_scales()

    def mousePressEvent(self, event: QMouseEvent):
        # Middle click, Right click, or Space+Left click initiates panning
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton) or (
            event.button() == Qt.MouseButton.LeftButton and self.space_pressed
        ):
            self.is_panning = True
            self.pan_start_pos = event.pos()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            event.accept()
            return

        # Manual box creation mode
        if self.add_box_mode and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self._clamp_scene_point(self.mapToScene(event.pos()))
            self.add_box_start = scene_pos
            self.temp_draw_rect = self.scene.addRect(
                QRectF(scene_pos, scene_pos),
                QPen(QColor(0, 230, 255), 2, Qt.PenStyle.DashLine),
                QBrush(QColor(0, 200, 255, 40))
            )
            event.accept()
            return

        super().mousePressEvent(event)

    def _clamp_scene_point(self, pt: QPointF) -> QPointF:
        bounds = self._image_bounds()
        if not self.keep_inside_image or not bounds:
            return pt
        img_w, img_h = bounds
        return QPointF(max(0.0, min(img_w, pt.x())), max(0.0, min(img_h, pt.y())))

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.is_panning:
            delta = event.pos() - self.pan_start_pos
            self.pan_start_pos = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return

        if self.add_box_mode and self.temp_draw_rect:
            cur_scene_pos = self._clamp_scene_point(self.mapToScene(event.pos()))
            if self.aspect_ratio is not None:
                dx = cur_scene_pos.x() - self.add_box_start.x()
                dy = cur_scene_pos.y() - self.add_box_start.y()
                sx = 1.0 if dx >= 0 else -1.0
                sy = 1.0 if dy >= 0 else -1.0
                w = abs(dx)
                h = w / self.aspect_ratio if self.aspect_ratio > 0 else abs(dy)
                if abs(dy) > h:
                    h = abs(dy)
                    w = h * self.aspect_ratio
                end_pt = self._clamp_scene_point(QPointF(
                    self.add_box_start.x() + sx * w,
                    self.add_box_start.y() + sy * h
                ))
                # Re-apply ratio within clamped bounds
                aw = abs(end_pt.x() - self.add_box_start.x())
                ah = abs(end_pt.y() - self.add_box_start.y())
                if ah > 0 and aw / ah > self.aspect_ratio:
                    aw = ah * self.aspect_ratio
                else:
                    ah = aw / self.aspect_ratio if self.aspect_ratio > 0 else ah
                cur_scene_pos = QPointF(
                    self.add_box_start.x() + sx * aw,
                    self.add_box_start.y() + sy * ah
                )
            rect = QRectF(self.add_box_start, cur_scene_pos).normalized()
            self.temp_draw_rect.setRect(rect)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.is_panning:
            self.is_panning = False
            if self.space_pressed:
                self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
            else:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            event.accept()
            return

        if self.add_box_mode and self.temp_draw_rect:
            rect = self.temp_draw_rect.rect()
            self.scene.removeItem(self.temp_draw_rect)
            self.temp_draw_rect = None
            self.set_add_box_mode(False)

            if rect.width() > 30 and rect.height() > 30:
                corners = np.array([
                    [rect.left(), rect.top()],
                    [rect.right(), rect.top()],
                    [rect.right(), rect.bottom()],
                    [rect.left(), rect.bottom()]
                ], dtype=np.float32)
                self.add_manual_crop(corners)
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected_crop()
            event.accept()
        elif key == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.space_pressed = True
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
            event.accept()
        elif key == Qt.Key.Key_0 and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.fit_in_view()
            event.accept()
        else:
            # Arrow key nudging for selected crop box
            sel = self.get_selected_crop()
            if sel:
                step = 10.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
                if key == Qt.Key.Key_Left:
                    sel.corners = sel._shift_inside_bounds(sel.corners - np.array([step, 0.0], dtype=np.float32))
                elif key == Qt.Key.Key_Right:
                    sel.corners = sel._shift_inside_bounds(sel.corners + np.array([step, 0.0], dtype=np.float32))
                elif key == Qt.Key.Key_Up:
                    sel.corners = sel._shift_inside_bounds(sel.corners - np.array([0.0, step], dtype=np.float32))
                elif key == Qt.Key.Key_Down:
                    sel.corners = sel._shift_inside_bounds(sel.corners + np.array([0.0, step], dtype=np.float32))
                else:
                    super().keyPressEvent(event)
                    return
                sel.update_geometry()
                self._on_crop_changed()
                event.accept()
                return

            super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.space_pressed = False
            if not self.is_panning:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            event.accept()
            return
        super().keyReleaseEvent(event)

    # --- Drag & Drop ---

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                ext = Path(file_path).suffix.lower()
                if ext in (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"):
                    self.file_dropped.emit(file_path)
                    event.acceptProposedAction()
                    return
        super().dropEvent(event)

    # --- Internal Signals ---

    def _on_crop_changed(self):
        self.crops_updated.emit()

    def _on_crop_selected(self, crop_id: int):
        for item in self.crop_items:
            if item.model.id != crop_id:
                item.setSelected(False)
        selected = self.get_selected_crop()
        self.selection_changed.emit(selected)

    def _on_handle_hover(self, point: Optional[QPointF], label: str):
        self.loupe.set_focus(point, label)

