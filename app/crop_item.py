"""
Interactive Rotated Crop Item for QGraphicsScene.
Supports 4 corner dragging, edge dragging, rotation handle, and whole-box movement,
with live Loupe widget updates for pixel-perfect adjustments.
"""

import math
from typing import Optional, Callable
import numpy as np
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal, QObject
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QBrush, QPolygonF, QFont, QCursor,
    QPainterPath, QPainterPathStroker
)
from PyQt6.QtWidgets import (
    QGraphicsItem, QGraphicsPolygonItem, QStyleOptionGraphicsItem, QWidget
)

from .photo_model import PhotoModel
from .detector import order_corners, straighten_quad


class CropSignals(QObject):
    changed = pyqtSignal()
    selected = pyqtSignal(int)  # crop_id
    handle_hover = pyqtSignal(object, str)  # (QPointF or None, label)
    handle_drag = pyqtSignal(object, str)   # (QPointF, label)


class CropBoxItem(QGraphicsPolygonItem):
    """
    Rotated quadrilateral crop box with draggable corner handles,
    edge handles, rotation handle, and whole-body translation.
    """

    HANDLE_NONE = -1
    HANDLE_TL = 0
    HANDLE_TR = 1
    HANDLE_BR = 2
    HANDLE_BL = 3
    HANDLE_ROT = 4
    HANDLE_BODY = 5
    HANDLE_TOP_EDGE = 6
    HANDLE_RIGHT_EDGE = 7
    HANDLE_BOT_EDGE = 8
    HANDLE_LEFT_EDGE = 9

    HANDLE_RADIUS = 6.5
    ROT_HANDLE_DIST = 34.0

    def _view_scale(self) -> float:
        """Returns the current scene-to-screen scale factor from the attached view."""
        scene = self.scene()
        if scene:
            views = scene.views()
            if views:
                s = abs(views[0].transform().m11())
                if s > 1e-4:
                    return s
        return 1.0

    def __init__(self, model: PhotoModel, parent=None):
        super().__init__(parent)
        self.model = model
        self.signals = CropSignals()

        # Corner points in scene coordinates: [TL, TR, BR, BL]
        self.corners = np.array(model.corners, dtype=np.float32)

        self.active_handle = self.HANDLE_NONE
        self.hover_handle = self.HANDLE_NONE
        self.drag_start_pos = QPointF()
        self.drag_start_corners = self.corners.copy()
        self.lock_rectangular = getattr(model, "lock_rectangular", True)
        self.aspect_ratio: Optional[float] = None  # width / height when locked
        self.keep_inside_image: bool = True
        self.image_bounds: Optional[tuple[float, float]] = None

        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(10)

        self.update_geometry()

    def update_geometry(self):
        """Updates the QGraphicsPolygon from self.corners."""
        poly = QPolygonF([
            QPointF(float(self.corners[0, 0]), float(self.corners[0, 1])),
            QPointF(float(self.corners[1, 0]), float(self.corners[1, 1])),
            QPointF(float(self.corners[2, 0]), float(self.corners[2, 1])),
            QPointF(float(self.corners[3, 0]), float(self.corners[3, 1])),
        ])
        self.setPolygon(poly)
        self.model.corners = self.corners.copy()
        self.update()

    def set_corners(self, new_corners: np.ndarray):
        """Sets new corner coordinates and re-renders."""
        self.corners = order_corners(new_corners)
        self.update_geometry()
        self.signals.changed.emit()

    def set_lock_rectangular(self, lock: bool):
        """Toggles between locked 90-degree rectangle and free quadrilateral skew."""
        self.lock_rectangular = lock
        self.model.lock_rectangular = lock

    def set_aspect_ratio(self, ratio: Optional[float], snap_now: bool = False):
        """Sets an optional width/height aspect ratio lock (None = free)."""
        self.aspect_ratio = ratio
        if snap_now and ratio is not None:
            pts = straighten_quad(self.corners)
            tl, tr, br, bl = pts
            center = pts.mean(axis=0)
            w_vec = tr - tl
            h_vec = bl - tl
            w_len = float(np.linalg.norm(w_vec))
            h_len = float(np.linalg.norm(h_vec))
            if w_len >= 1e-4 and h_len >= 1e-4:
                u = w_vec / w_len
                v = h_vec / h_len
                # Preserve area approximately while enforcing w_len / h_len = ratio
                area = max(w_len * h_len, 225.0)
                new_h = max(15.0, math.sqrt(area / ratio))
                new_w = max(15.0, new_h * ratio)
                new_pts = np.array([
                    center - (new_w / 2.0) * u - (new_h / 2.0) * v,
                    center + (new_w / 2.0) * u - (new_h / 2.0) * v,
                    center + (new_w / 2.0) * u + (new_h / 2.0) * v,
                    center - (new_w / 2.0) * u + (new_h / 2.0) * v,
                ], dtype=np.float32)
                if self.keep_inside_image and self.image_bounds is not None:
                    new_pts = self._fit_box_inside_bounds(new_pts, center, u, v, new_w, new_h)
                self.corners = new_pts
                self.update_geometry()
                self.signals.changed.emit()

    def _fit_box_inside_bounds(
        self, pts: np.ndarray, center: np.ndarray, u: np.ndarray, v: np.ndarray, w_len: float, h_len: float
    ) -> np.ndarray:
        """Shifts and, if needed, uniformly scales a centered box to stay inside image_bounds."""
        if not self.image_bounds:
            return pts
        img_w, img_h = self.image_bounds
        pts = self._shift_inside_bounds(pts)
        min_x, max_x = float(pts[:, 0].min()), float(pts[:, 0].max())
        min_y, max_y = float(pts[:, 1].min()), float(pts[:, 1].max())
        span_x = max(max_x - min_x, 1e-4)
        span_y = max(max_y - min_y, 1e-4)
        if span_x > img_w or span_y > img_h:
            scale = min(img_w / span_x, img_h / span_y)
            nw, nh = max(15.0, w_len * scale), max(15.0, h_len * scale)
            c = pts.mean(axis=0)
            pts = np.array([
                c - (nw / 2.0) * u - (nh / 2.0) * v,
                c + (nw / 2.0) * u - (nh / 2.0) * v,
                c + (nw / 2.0) * u + (nh / 2.0) * v,
                c - (nw / 2.0) * u + (nh / 2.0) * v,
            ], dtype=np.float32)
            pts = self._shift_inside_bounds(pts)
        return pts

    def _shift_inside_bounds(self, pts: np.ndarray) -> np.ndarray:
        """Translates pts so its bounding box stays inside [0, img_w] x [0, img_h] when possible."""
        if not self.keep_inside_image or not self.image_bounds:
            return pts
        img_w, img_h = self.image_bounds
        out = pts.copy()
        min_x, max_x = float(out[:, 0].min()), float(out[:, 0].max())
        min_y, max_y = float(out[:, 1].min()), float(out[:, 1].max())
        if max_x - min_x <= img_w:
            if min_x < 0.0:
                out[:, 0] -= min_x
            elif max_x > img_w:
                out[:, 0] -= (max_x - img_w)
        if max_y - min_y <= img_h:
            if min_y < 0.0:
                out[:, 1] -= min_y
            elif max_y > img_h:
                out[:, 1] -= (max_y - img_h)
        return out

    def _clamp_point(self, pt: np.ndarray) -> np.ndarray:
        if not self.keep_inside_image or not self.image_bounds:
            return pt
        img_w, img_h = self.image_bounds
        return np.array([
            float(np.clip(pt[0], 0.0, img_w)),
            float(np.clip(pt[1], 0.0, img_h))
        ], dtype=np.float32)

    def _max_scale_inside_bounds(self, anchor: np.ndarray, vec: np.ndarray) -> float:
        """Returns the maximum factor t in [0, 1] such that anchor + t * vec stays inside image_bounds."""
        if not self.keep_inside_image or not self.image_bounds:
            return 1.0
        img_w, img_h = self.image_bounds
        t_max = 1.0
        for axis, limit in ((0, img_w), (1, img_h)):
            v = float(vec[axis])
            a = float(anchor[axis])
            if v > 1e-6:
                t_max = min(t_max, (limit - a) / v)
            elif v < -1e-6:
                t_max = min(t_max, -a / v)
        return max(0.0, t_max)

    def straighten(self):
        """Snaps the box into an exact 90-degree rectangle aligned with its current orientation."""
        self.corners = straighten_quad(self.corners)
        self.update_geometry()
        self.signals.changed.emit()

    def get_corners(self) -> np.ndarray:
        return self.corners.copy()

    def get_center(self) -> QPointF:
        c = self.corners.mean(axis=0)
        return QPointF(float(c[0]), float(c[1]))

    def get_rotation_handle_pos(self) -> QPointF:
        """Computes rotation handle position extended from the top edge in screen-scaled units."""
        tl = self.corners[0]
        tr = self.corners[1]
        mid_top = (tl + tr) / 2.0
        edge_vec = tr - tl
        edge_len = np.linalg.norm(edge_vec)
        if edge_len < 1e-4:
            normal = np.array([0.0, -1.0], dtype=np.float32)
        else:
            # Perpendicular vector pointing outward (counter-clockwise)
            normal = np.array([edge_vec[1], -edge_vec[0]], dtype=np.float32) / edge_len

        inv_scale = 1.0 / self._view_scale()
        rot_pos = mid_top + normal * (self.ROT_HANDLE_DIST * inv_scale)
        return QPointF(float(rot_pos[0]), float(rot_pos[1]))

    def get_edge_midpoints(self) -> list[QPointF]:
        """Returns midpoints of Top, Right, Bottom, Left edges."""
        tl, tr, br, bl = self.corners
        return [
            QPointF(float((tl[0] + tr[0]) / 2), float((tl[1] + tr[1]) / 2)),
            QPointF(float((tr[0] + br[0]) / 2), float((tr[1] + br[1]) / 2)),
            QPointF(float((br[0] + bl[0]) / 2), float((br[1] + bl[1]) / 2)),
            QPointF(float((bl[0] + tl[0]) / 2), float((bl[1] + tl[1]) / 2)),
        ]

    def boundingRect(self) -> QRectF:
        inv_scale = 1.0 / self._view_scale()
        pad = 25.0 * inv_scale
        rect = super().boundingRect()
        rot_pt = self.get_rotation_handle_pos()
        rect = rect.united(QRectF(rot_pt.x() - pad, rot_pt.y() - pad, pad * 2.0, pad * 2.0))
        return rect.adjusted(-pad, -pad, pad, pad)

    def shape(self) -> QPainterPath:
        """
        Custom shape including the polygon, the extended rotation handle,
        stem line, and corner handles for reliable mouse hit-testing at any zoom.
        """
        inv_scale = 1.0 / self._view_scale()
        path = QPainterPath()
        path.addPolygon(self.polygon())

        # Include rotation handle and stem
        rot_pt = self.get_rotation_handle_pos()
        rot_hit_r = (self.HANDLE_RADIUS + 12.0) * inv_scale
        path.addEllipse(rot_pt, rot_hit_r, rot_hit_r)

        tl = self.corners[0]
        tr = self.corners[1]
        mid_top = QPointF(float((tl[0] + tr[0]) / 2), float((tl[1] + tr[1]) / 2))
        path.moveTo(mid_top)
        path.lineTo(rot_pt)

        # Include corner handles
        corner_hit_r = (self.HANDLE_RADIUS + 8.0) * inv_scale
        for idx in range(4):
            c_pt = QPointF(float(self.corners[idx, 0]), float(self.corners[idx, 1]))
            path.addEllipse(c_pt, corner_hit_r, corner_hit_r)

        # Stroke to broaden line and edge hit detection
        stroker = QPainterPathStroker()
        stroker.setWidth(16.0 * inv_scale)
        return path.united(stroker.createStroke(path))

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        is_sel = self.isSelected() or self.model.is_selected
        inv_scale = 1.0 / self._view_scale()

        # 1. Fill polygon with semi-transparent color
        if is_sel:
            fill_color = QColor(0, 190, 255, 60)
            stroke_color = QColor(0, 225, 255)
            stroke_width = 2.2 * inv_scale
        else:
            fill_color = QColor(0, 160, 220, 35)
            stroke_color = QColor(0, 180, 230)
            stroke_width = 1.5 * inv_scale

        painter.setBrush(QBrush(fill_color))
        painter.setPen(QPen(stroke_color, stroke_width, Qt.PenStyle.SolidLine))
        painter.drawPolygon(self.polygon())

        # 2. Draw stem line to rotation handle
        tl = self.corners[0]
        tr = self.corners[1]
        mid_top = QPointF(float((tl[0] + tr[0]) / 2), float((tl[1] + tr[1]) / 2))
        rot_pt = self.get_rotation_handle_pos()

        stem_pen = QPen(stroke_color, 1.5 * inv_scale, Qt.PenStyle.DashLine)
        painter.setPen(stem_pen)
        painter.drawLine(mid_top, rot_pt)

        # 3. Draw Rotation Handle
        rot_hover = (self.hover_handle == self.HANDLE_ROT or self.active_handle == self.HANDLE_ROT)
        rot_radius = (self.HANDLE_RADIUS + 2.0 + (2.5 if rot_hover else 0.0)) * inv_scale
        painter.setBrush(QBrush(QColor(255, 235, 50) if rot_hover else QColor(255, 195, 0)))
        painter.setPen(QPen(QColor(15, 20, 30), 1.8 * inv_scale))
        painter.drawEllipse(rot_pt, rot_radius, rot_radius)

        # 4. Draw Corner Handles (TL, TR, BR, BL)
        for idx in range(4):
            pt = QPointF(float(self.corners[idx, 0]), float(self.corners[idx, 1]))
            is_hover = (self.hover_handle == idx or self.active_handle == idx)
            rad = (self.HANDLE_RADIUS + (2.5 if is_hover else 0.0)) * inv_scale

            if is_hover:
                c_brush = QBrush(QColor(0, 255, 170))  # Bright mint green when hovering
                c_pen = QPen(QColor(10, 30, 20), 1.8 * inv_scale)
            else:
                c_brush = QBrush(QColor(255, 255, 255))
                c_pen = QPen(QColor(0, 150, 230), 1.8 * inv_scale)

            painter.setBrush(c_brush)
            painter.setPen(c_pen)
            painter.drawEllipse(pt, rad, rad)

        # 5. Draw Edge Midpoint Handles (smaller squares)
        edge_pts = self.get_edge_midpoints()
        for idx, e_pt in enumerate(edge_pts):
            handle_code = self.HANDLE_TOP_EDGE + idx
            is_hover = (self.hover_handle == handle_code or self.active_handle == handle_code)
            size = (8.0 if is_hover else 6.0) * inv_scale
            painter.setBrush(QBrush(QColor(0, 255, 220) if is_hover else QColor(200, 220, 240)))
            painter.setPen(QPen(QColor(20, 30, 45), 1.2 * inv_scale))
            painter.drawRect(QRectF(e_pt.x() - size / 2, e_pt.y() - size / 2, size, size))

        # 6. Draw Badge / Label at center in fixed screen-pixel size
        center_pt = self.get_center()
        badge_text = f"Photo #{self.model.id}"
        if self.model.date_str:
            badge_text += f" | {self.model.date_str}"
        w_px, h_px = self.model.dimensions
        badge_text += f" ({w_px}x{h_px})"

        painter.save()
        painter.translate(center_pt)
        painter.scale(inv_scale, inv_scale)

        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(badge_text) + 16
        text_h = fm.height() + 8

        badge_rect = QRectF(-text_w / 2.0, -text_h / 2.0, text_w, text_h)
        painter.setBrush(QBrush(QColor(18, 24, 38, 220)))
        painter.setPen(QPen(stroke_color, 1.2))
        painter.drawRoundedRect(badge_rect, 6, 6)

        painter.setPen(QColor(245, 250, 255))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)
        painter.restore()

    def hit_test_handle(self, pos: QPointF) -> int:
        """Determines which handle is hit at pos (using screen-scaled hit radii)."""
        inv_scale = 1.0 / self._view_scale()

        # 1. Test rotation handle (generous hit target)
        rot_pt = self.get_rotation_handle_pos()
        dist_rot = math.hypot(pos.x() - rot_pt.x(), pos.y() - rot_pt.y())
        if dist_rot <= (self.HANDLE_RADIUS + 12.0) * inv_scale:
            return self.HANDLE_ROT

        # 2. Test corner handles
        for idx in range(4):
            c_pt = QPointF(float(self.corners[idx, 0]), float(self.corners[idx, 1]))
            dist_c = math.hypot(pos.x() - c_pt.x(), pos.y() - c_pt.y())
            if dist_c <= (self.HANDLE_RADIUS + 8.0) * inv_scale:
                return idx

        # 3. Test edge handles
        edge_pts = self.get_edge_midpoints()
        for idx, e_pt in enumerate(edge_pts):
            dist_e = math.hypot(pos.x() - e_pt.x(), pos.y() - e_pt.y())
            if dist_e <= (self.HANDLE_RADIUS + 6.0) * inv_scale:
                return self.HANDLE_TOP_EDGE + idx

        # 4. Test inside polygon
        if self.polygon().containsPoint(pos, Qt.FillRule.OddEvenFill):
            return self.HANDLE_BODY

        return self.HANDLE_NONE

    def hoverMoveEvent(self, event):
        pos = event.pos()
        handle = self.hit_test_handle(pos)
        self.hover_handle = handle

        # Update cursor and emit loupe hover signal
        handle_names = {
            self.HANDLE_TL: "Top-Left Corner",
            self.HANDLE_TR: "Top-Right Corner",
            self.HANDLE_BR: "Bottom-Right Corner",
            self.HANDLE_BL: "Bottom-Left Corner",
            self.HANDLE_ROT: "Rotation Handle",
            self.HANDLE_TOP_EDGE: "Top Edge Resize",
            self.HANDLE_RIGHT_EDGE: "Right Edge Resize",
            self.HANDLE_BOT_EDGE: "Bottom Edge Resize",
            self.HANDLE_LEFT_EDGE: "Left Edge Resize",
            self.HANDLE_BODY: f"Move Photo #{self.model.id}"
        }

        if handle in (self.HANDLE_TL, self.HANDLE_TR, self.HANDLE_BR, self.HANDLE_BL):
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
            pt = QPointF(float(self.corners[handle, 0]), float(self.corners[handle, 1]))
            self.signals.handle_hover.emit(pt, f"Photo #{self.model.id} {handle_names[handle]}")
        elif handle == self.HANDLE_ROT:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.signals.handle_hover.emit(self.get_rotation_handle_pos(), f"Photo #{self.model.id} {handle_names[handle]}")
        elif handle in (self.HANDLE_TOP_EDGE, self.HANDLE_BOT_EDGE):
            self.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))
        elif handle in (self.HANDLE_RIGHT_EDGE, self.HANDLE_LEFT_EDGE):
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        elif handle == self.HANDLE_BODY:
            self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            self.signals.handle_hover.emit(None, "")

        self.update()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.hover_handle = self.HANDLE_NONE
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self.signals.handle_hover.emit(None, "")
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos()
            self.active_handle = self.hit_test_handle(pos)
            self.drag_start_pos = pos
            self.drag_start_corners = self.corners.copy()

            self.setSelected(True)
            self.signals.selected.emit(self.model.id)

            if self.active_handle in (self.HANDLE_TL, self.HANDLE_TR, self.HANDLE_BR, self.HANDLE_BL):
                pt = QPointF(float(self.corners[self.active_handle, 0]), float(self.corners[self.active_handle, 1]))
                self.signals.handle_drag.emit(pt, f"Adjusting Photo #{self.model.id} Corner")
            elif self.active_handle == self.HANDLE_ROT:
                rot_pt = self.get_rotation_handle_pos()
                self.signals.handle_drag.emit(rot_pt, f"Rotating Photo #{self.model.id}")

            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.active_handle == self.HANDLE_NONE:
            super().mouseMoveEvent(event)
            return

        cur_pos = event.pos()
        delta = cur_pos - self.drag_start_pos
        dx = float(delta.x())
        dy = float(delta.y())

        # 1. Corner dragging
        if self.active_handle in (self.HANDLE_TL, self.HANDLE_TR, self.HANDLE_BR, self.HANDLE_BL):
            # Shift key inverts the rectangular lock setting
            shift_pressed = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            is_rect = self.lock_rectangular ^ shift_pressed

            if is_rect:
                self._resize_corner_rectangular(self.active_handle, cur_pos)
            else:
                new_pt = np.array([
                    self.drag_start_corners[self.active_handle, 0] + dx,
                    self.drag_start_corners[self.active_handle, 1] + dy
                ], dtype=np.float32)
                self.corners[self.active_handle] = self._clamp_point(new_pt)

            self.update_geometry()
            pt = QPointF(float(self.corners[self.active_handle, 0]), float(self.corners[self.active_handle, 1]))
            mode_tag = " [Square 90°]" if is_rect else " [Skewed/Quad]"
            self.signals.handle_drag.emit(pt, f"Photo #{self.model.id} Corner {self.active_handle + 1}{mode_tag}")
            self.signals.changed.emit()

        # 2. Whole body translation
        elif self.active_handle == self.HANDLE_BODY:
            moved = self.drag_start_corners + np.array([dx, dy], dtype=np.float32)
            self.corners = self._shift_inside_bounds(moved)
            self.update_geometry()
            self.signals.changed.emit()

        # 3. Rotation handle dragging
        elif self.active_handle == self.HANDLE_ROT:
            center = self.drag_start_corners.mean(axis=0)

            # Compute initial rotation handle position from drag_start_corners
            tl = self.drag_start_corners[0]
            tr = self.drag_start_corners[1]
            mid_top = (tl + tr) / 2.0
            edge_vec = tr - tl
            edge_len = np.linalg.norm(edge_vec)
            if edge_len < 1e-4:
                normal = np.array([0.0, -1.0], dtype=np.float32)
            else:
                normal = np.array([edge_vec[1], -edge_vec[0]], dtype=np.float32) / edge_len
            inv_scale = 1.0 / self._view_scale()
            start_rot_pt = mid_top + normal * (self.ROT_HANDLE_DIST * inv_scale)

            init_vec = start_rot_pt - center
            cur_vec = np.array([cur_pos.x() - center[0], cur_pos.y() - center[1]], dtype=np.float32)

            init_angle = math.atan2(float(init_vec[1]), float(init_vec[0]))
            cur_angle = math.atan2(float(cur_vec[1]), float(cur_vec[0]))
            angle_delta = cur_angle - init_angle

            # Rotate corners around center
            cos_a = math.cos(angle_delta)
            sin_a = math.sin(angle_delta)
            R = np.array([[cos_a, -sin_a], [sin_a, cos_a]], dtype=np.float32)

            rel_corners = self.drag_start_corners - center
            rotated = self._shift_inside_bounds((rel_corners @ R.T) + center)
            if self.keep_inside_image and self.image_bounds is not None:
                img_w, img_h = self.image_bounds
                if (
                    rotated[:, 0].min() >= -0.5 and rotated[:, 0].max() <= img_w + 0.5
                    and rotated[:, 1].min() >= -0.5 and rotated[:, 1].max() <= img_h + 0.5
                ):
                    self.corners = rotated
            else:
                self.corners = rotated
            self.update_geometry()
            self.signals.handle_drag.emit(self.get_rotation_handle_pos(), f"Rotating Photo #{self.model.id}")
            self.signals.changed.emit()

        # 4. Edge resizing
        elif self.active_handle in (self.HANDLE_TOP_EDGE, self.HANDLE_RIGHT_EDGE, self.HANDLE_BOT_EDGE, self.HANDLE_LEFT_EDGE):
            edge_idx = self.active_handle - self.HANDLE_TOP_EDGE
            self._resize_edge(edge_idx, dx, dy)
            self.update_geometry()
            self.signals.changed.emit()

        event.accept()

    def _resize_corner_rectangular(self, handle_idx: int, cur_pos: QPointF):
        """
        Resizes the crop box keeping all four corners strictly orthogonal (90 degrees),
        using the opposite corner as the fixed anchor.
        """
        opp_idx = (handle_idx + 2) % 4
        anchor = self.drag_start_corners[opp_idx]

        # Adjacent corners to handle_idx:
        adj1_idx = (handle_idx + 3) % 4
        adj2_idx = (handle_idx + 1) % 4

        v1 = self.drag_start_corners[adj1_idx] - anchor
        len1 = float(np.linalg.norm(v1))
        if len1 < 1e-4:
            u1 = np.array([1.0, 0.0], dtype=np.float32)
        else:
            u1 = v1 / len1

        v2 = self.drag_start_corners[adj2_idx] - anchor
        # Construct u2 strictly perpendicular to u1, pointing towards v2
        perp = np.array([-u1[1], u1[0]], dtype=np.float32)
        if float(np.dot(perp, v2)) < 0:
            perp = -perp
        u2 = perp

        # Mouse coordinate relative to anchor
        cur_xy = np.array([float(cur_pos.x()), float(cur_pos.y())], dtype=np.float32)
        mouse_vec = cur_xy - anchor

        # Projections onto axes
        d1 = max(15.0, float(np.dot(mouse_vec, u1)))
        d2 = max(15.0, float(np.dot(mouse_vec, u2)))

        # Enforce locked aspect ratio (width / height) if active
        if self.aspect_ratio is not None:
            r = self.aspect_ratio
            # Determine which axis corresponds to width vs height
            u1_is_width = abs(float(u1[0])) >= abs(float(u2[0]))
            if u1_is_width:
                t = max(15.0, (d1 * r + d2) / (r * r + 1.0))
                d1, d2 = max(15.0, t * r), t
            else:
                t = max(15.0, (d2 * r + d1) / (r * r + 1.0))
                d2, d1 = max(15.0, t * r), t

        # Clamp inside image bounds if enabled
        if self.keep_inside_image and self.image_bounds is not None:
            if self.aspect_ratio is not None:
                t_max = min(
                    self._max_scale_inside_bounds(anchor, d1 * u1),
                    self._max_scale_inside_bounds(anchor, d2 * u2),
                    self._max_scale_inside_bounds(anchor, d1 * u1 + d2 * u2),
                )
                d1 = max(15.0, d1 * t_max)
                d2 = max(15.0, d2 * t_max)
            else:
                t1 = self._max_scale_inside_bounds(anchor, d1 * u1)
                d1 = max(15.0, d1 * t1)
                t2 = self._max_scale_inside_bounds(anchor, d2 * u2)
                d2 = max(15.0, d2 * t2)
                t_diag = self._max_scale_inside_bounds(anchor + d1 * u1, d2 * u2)
                if t_diag < 1.0:
                    d2 = max(15.0, d2 * t_diag)

        new_corners = self.drag_start_corners.copy()
        new_corners[opp_idx] = anchor
        new_corners[adj1_idx] = anchor + d1 * u1
        new_corners[adj2_idx] = anchor + d2 * u2
        new_corners[handle_idx] = anchor + d1 * u1 + d2 * u2

        self.corners = new_corners

    def _resize_edge(self, edge_idx: int, dx: float, dy: float):
        """Displaces the two corners of an edge along the edge's perpendicular normal."""
        # Top: 0-1, Right: 1-2, Bottom: 2-3, Left: 3-0
        corner_pairs = [(0, 1), (1, 2), (2, 3), (3, 0)]
        opp_pairs = [(3, 2), (0, 3), (1, 0), (2, 1)]
        c1_idx, c2_idx = corner_pairs[edge_idx]
        o1_idx, o2_idx = opp_pairs[edge_idx]

        c1 = self.drag_start_corners[c1_idx]
        c2 = self.drag_start_corners[c2_idx]
        o1 = self.drag_start_corners[o1_idx]
        o2 = self.drag_start_corners[o2_idx]
        edge_vec = c2 - c1
        edge_len = float(np.linalg.norm(edge_vec))
        if edge_len < 1e-4:
            return

        # Normal vector pointing away from the opposite edge
        normal = np.array([edge_vec[1], -edge_vec[0]], dtype=np.float32) / edge_len
        if float(np.dot(normal, c1 - o1)) < 0:
            normal = -normal

        cur_depth = float(np.dot(c1 - o1, normal))
        proj = (dx * float(normal[0])) + (dy * float(normal[1]))
        new_depth = max(15.0, cur_depth + proj)

        if self.aspect_ratio is not None:
            r = self.aspect_ratio
            # Top/Bottom edges change height; Left/Right edges change width
            if edge_idx in (0, 2):
                new_edge_len = max(15.0, new_depth * r)
            else:
                new_edge_len = max(15.0, new_depth / r)

            u_edge = edge_vec / edge_len
            mid_opp = (o1 + o2) / 2.0
            mid_edge = mid_opp + normal * new_depth
            new_c1 = mid_edge - (new_edge_len / 2.0) * u_edge
            new_c2 = mid_edge + (new_edge_len / 2.0) * u_edge
            new_o1 = mid_opp - (new_edge_len / 2.0) * u_edge
            new_o2 = mid_opp + (new_edge_len / 2.0) * u_edge

            if self.keep_inside_image and self.image_bounds is not None:
                img_w, img_h = self.image_bounds
                candidate = np.array([new_c1, new_c2, new_o1, new_o2], dtype=np.float32)
                if (
                    candidate[:, 0].min() < 0.0 or candidate[:, 0].max() > img_w
                    or candidate[:, 1].min() < 0.0 or candidate[:, 1].max() > img_h
                ):
                    return

            self.corners[c1_idx] = new_c1
            self.corners[c2_idx] = new_c2
            self.corners[o1_idx] = new_o1
            self.corners[o2_idx] = new_o2
            return

        delta_depth = new_depth - cur_depth
        shift = normal * delta_depth
        t1 = self._max_scale_inside_bounds(c1, shift)
        t2 = self._max_scale_inside_bounds(c2, shift)
        t = min(t1, t2)
        self.corners[c1_idx] = c1 + shift * t
        self.corners[c2_idx] = c2 + shift * t

    def mouseReleaseEvent(self, event):
        if self.active_handle != self.HANDLE_NONE:
            self.active_handle = self.HANDLE_NONE
            self.signals.handle_hover.emit(None, "")
            self.update()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

