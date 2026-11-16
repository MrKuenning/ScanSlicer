"""
Scanner bed photo detection engine.
Detects multiple crooked or upright photos on flatbed scanner images,
extracts true rectangular bounding boxes, and performs perspective deskewing.
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional
import cv2
import numpy as np


@dataclass
class DetectedCrop:
    id: int
    corners: np.ndarray  # (4, 2) float32: [Top-Left, Top-Right, Bottom-Right, Bottom-Left]
    angle: float         # Rotation angle in degrees
    area: float
    confidence: float
    rotation_offset: int = 0  # User manual 90-degree steps (0, 90, 180, 270)


def order_corners(pts: np.ndarray) -> np.ndarray:
    """
    Orders 4 points into [Top-Left, Top-Right, Bottom-Right, Bottom-Left].
    Maintains clockwise orientation starting from top-left.
    """
    pts = pts.reshape(4, 2).astype(np.float32)
    rect = np.zeros((4, 2), dtype=np.float32)

    # Sum of coordinates: top-left has smallest sum, bottom-right has largest sum
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]

    # Difference of coordinates (y - x): top-right has smallest diff, bottom-left has largest diff
    diff = np.diff(pts, axis=1).flatten()
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]

    return rect


def snap_rect_angle(rect: Tuple[Tuple[float, float], Tuple[float, float], float], snap_threshold: float = 3.0):
    """
    Normalizes a cv2.minAreaRect and snaps near-upright angles within snap_threshold
    to an exact 0.0 degree rectangular orientation.
    """
    (cx, cy), (w, h), angle = rect

    # OpenCV 4.5+ minAreaRect angle convention
    if w < h:
        w, h = h, w
        angle += 90.0

    while angle > 45.0:
        angle -= 90.0
    while angle <= -45.0:
        angle += 90.0

    # Snap to upright if within snap_threshold
    if abs(angle) < snap_threshold:
        angle = 0.0

    return (cx, cy), (w, h), angle


def get_rect_corners(rect: Tuple[Tuple[float, float], Tuple[float, float], float]) -> np.ndarray:
    """
    Converts a normalized (center, size, angle) rectangle into 4 ordered corners [TL, TR, BR, BL].
    Guarantees strict 90-degree right angles.
    """
    (cx, cy), (w, h), angle = rect

    if angle == 0.0:
        hw = w / 2.0
        hh = h / 2.0
        return np.array([
            [cx - hw, cy - hh],
            [cx + hw, cy - hh],
            [cx + hw, cy + hh],
            [cx - hw, cy + hh]
        ], dtype=np.float32)

    box = cv2.boxPoints(((cx, cy), (w, h), angle)).astype(np.float32)
    return order_corners(box)


def straighten_quad(corners: np.ndarray) -> np.ndarray:
    """
    Snaps any arbitrary quadrilateral into an exact 90-degree rectangle
    centered at the quad's centroid and aligned with its principal width axis.
    """
    pts = order_corners(corners)
    tl, tr, br, bl = pts
    center = pts.mean(axis=0)

    w_vec = ((tr - tl) + (br - bl)) / 2.0
    w_len = np.linalg.norm(w_vec)
    if w_len < 1e-4:
        return pts

    u = w_vec / w_len
    # Perpendicular vector pointing downwards in image coords (y down)
    v = np.array([-u[1], u[0]], dtype=np.float32)
    h_vec = ((bl - tl) + (br - tr)) / 2.0
    if np.dot(v, h_vec) < 0:
        v = -v
    h_len = np.linalg.norm(h_vec)

    new_tl = center - (w_len / 2.0) * u - (h_len / 2.0) * v
    new_tr = center + (w_len / 2.0) * u - (h_len / 2.0) * v
    new_br = center + (w_len / 2.0) * u + (h_len / 2.0) * v
    new_bl = center - (w_len / 2.0) * u + (h_len / 2.0) * v

    return np.array([new_tl, new_tr, new_br, new_bl], dtype=np.float32)


def detect_scanner_photos(
    image: np.ndarray,
    sensitivity: int = 50,
    min_area_ratio: float = 0.015,
    max_area_ratio: float = 0.90
) -> List[DetectedCrop]:
    """
    Detects photos on a flatbed scanner bed or album page.
    Always fits clean, non-distorted rotated rectangles.
    
    :param image: BGR numpy array of the scanned image.
    :param sensitivity: 1 to 100 slider value (50 is default).
    :param min_area_ratio: Minimum photo area relative to total image area.
    :param max_area_ratio: Maximum photo area relative to total image area.
    :return: List of DetectedCrop items sorted naturally (top-to-bottom, left-to-right).
    """
    if image is None or image.size == 0:
        return []

    h, w = image.shape[:2]
    total_area = float(h * w)

    # 1. Downscale for noise-resistant processing if image is very large
    max_dim = 1400
    scale = 1.0
    if max(h, w) > max_dim:
        scale = max_dim / float(max(h, w))
        work_img = cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    else:
        work_img = image.copy()

    wh, ww = work_img.shape[:2]

    # 2. Sample outer borders to estimate scanner platen background color
    border_width = max(6, int(min(wh, ww) * 0.02))
    borders = np.concatenate([
        work_img[0:border_width, :].reshape(-1, 3),
        work_img[-border_width:, :].reshape(-1, 3),
        work_img[:, 0:border_width].reshape(-1, 3),
        work_img[:, -border_width:].reshape(-1, 3)
    ], axis=0)
    bg_color = np.median(borders, axis=0)

    # 3. Method A: Perceptual LAB Color distance from background
    work_lab = cv2.cvtColor(work_img, cv2.COLOR_BGR2LAB)
    bg_lab = cv2.cvtColor(np.uint8([[bg_color]]), cv2.COLOR_BGR2LAB)[0, 0]
    diff_lab = np.linalg.norm(work_lab.astype(np.float32) - bg_lab.astype(np.float32), axis=2)

    # Adaptive Otsu calculation on distance map
    max_d = max(float(diff_lab.max()), 1.0)
    diff_u8 = np.clip(diff_lab * (255.0 / max_d), 0, 255).astype(np.uint8)
    otsu_val, _ = cv2.threshold(diff_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    lab_otsu = (otsu_val / 255.0) * max_d

    # Sensitivity mapping: safely scales the adaptive threshold
    # Higher sensitivity = slightly lower threshold (detects subtler borders)
    # Never collapses to 0 (which would select entire image) or blows up to infinity
    factor = 1.35 - (sensitivity / 100.0) * 0.70
    thresh_val = float(np.clip(lab_otsu * factor, 12.0, 50.0))
    mask_diff = (diff_lab > thresh_val).astype(np.uint8) * 255

    # 4. Method B: Bilateral-filtered edge detection
    gray = cv2.cvtColor(work_img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.bilateralFilter(gray, 7, 50, 50)
    edges = cv2.Canny(blurred, 30, 90)

    # Combine distance mask and edges
    combined_mask = cv2.bitwise_or(mask_diff, edges)

    # 5. Small morphological closing (5x5) to prevent bridging narrow photo gutters
    kernel_size = 5
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    closed = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel)

    # 6. Find contours with full hierarchy (to detect and discard merged containers)
    contours, hierarchy = cv2.findContours(closed, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    min_area = total_area * min_area_ratio * (scale * scale)
    max_area = total_area * max_area_ratio * (scale * scale)

    raw_candidates = []
    if hierarchy is not None and len(contours) > 0:
        hier = hierarchy[0]
        for idx, c in enumerate(contours):
            area = cv2.contourArea(c)
            if area < min_area or area > max_area:
                continue

            rect = cv2.minAreaRect(c)
            snapped_rect = snap_rect_angle(rect, snap_threshold=3.0)
            (cx, cy), (rw, rh), angle = snapped_rect

            # Reject slivers with extreme aspect ratio
            if min(rw, rh) < 25:
                continue
            aspect = max(rw, rh) / (min(rw, rh) + 1e-5)
            if aspect > 12:
                continue

            raw_candidates.append({
                "index": idx,
                "area": area,
                "rect": snapped_rect,
                "contour": c,
                "has_child": (hier[idx][2] != -1)
            })

    # Discard merged parent containers that enclose valid child photos
    filtered_candidates = []
    for cand in raw_candidates:
        c_rect = cand["rect"]
        is_merged_container = False

        # If cand encloses one or more other valid candidates, drop cand
        for other in raw_candidates:
            if other["index"] == cand["index"]:
                continue
            if other["area"] >= cand["area"]:
                continue

            ret, pts = cv2.rotatedRectangleIntersection(c_rect, other["rect"])
            if pts is not None and len(pts) >= 3:
                inter_area = cv2.contourArea(pts)
                if inter_area / other["area"] > 0.60:
                    # cand encloses other photo -> cand is a merged multi-photo blob!
                    is_merged_container = True
                    break

        if not is_merged_container:
            filtered_candidates.append(cand)

    # 7. Non-Maximum Suppression to remove overlapping boxes
    kept_rects = []
    # Sort candidates by area ascending (prefer individual photos over merged blobs)
    filtered_candidates.sort(key=lambda x: x["area"])

    for cand in filtered_candidates:
        c_rect = cand["rect"]
        c_area = cand["area"]
        is_duplicate = False

        for k_rect, k_area in kept_rects:
            ret, pts = cv2.rotatedRectangleIntersection(c_rect, k_rect)
            if pts is not None and len(pts) >= 3:
                inter_area = cv2.contourArea(pts)
                min_a = min(c_area, k_area)
                # If overlap exceeds 35% of either box, treat as duplicate
                if inter_area / min_a > 0.35:
                    is_duplicate = True
                    break

        if not is_duplicate:
            kept_rects.append((c_rect, c_area))

    # 8. Build final DetectedCrop items
    detected: List[DetectedCrop] = []
    for idx, (snapped_rect, area) in enumerate(kept_rects, start=1):
        (cx, cy), (rw, rh), angle = snapped_rect

        # Rescale rectangle back to original image coordinate space
        orig_cx = cx / scale
        orig_cy = cy / scale
        orig_rw = rw / scale
        orig_rh = rh / scale
        orig_rect = ((orig_cx, orig_cy), (orig_rw, orig_rh), angle)

        # Get guaranteed 90-degree corners
        corners = get_rect_corners(orig_rect)
        orig_area = orig_rw * orig_rh

        detected.append(DetectedCrop(
            id=idx,
            corners=corners,
            angle=float(angle),
            area=float(orig_area),
            confidence=0.95
        ))

    # Sort crops naturally: top-to-bottom, left-to-right
    detected.sort(key=lambda item: (item.corners[:, 1].mean() // 150, item.corners[:, 0].mean()))

    for idx, item in enumerate(detected, start=1):
        item.id = idx

    return detected


def extract_deskewed_crop(
    image: np.ndarray,
    corners: np.ndarray,
    rotation_offset: int = 0
) -> np.ndarray:
    """
    Deskews and crops a quadrilateral region from the image using perspective transform.
    
    :param image: Source BGR image.
    :param corners: (4, 2) array of [Top-Left, Top-Right, Bottom-Right, Bottom-Left].
    :param rotation_offset: Additional 90-degree rotations (0, 90, 180, 270).
    :return: Undistorted, deskewed rectangular image.
    """
    pts = order_corners(corners)
    (tl, tr, br, bl) = pts

    width_top = np.linalg.norm(tr - tl)
    width_bot = np.linalg.norm(br - bl)
    max_w = max(int(round(width_top)), int(round(width_bot)))

    height_r = np.linalg.norm(br - tr)
    height_l = np.linalg.norm(bl - tl)
    max_h = max(int(round(height_r)), int(round(height_l)))

    if max_w <= 2 or max_h <= 2:
        return np.zeros((10, 10, 3), dtype=np.uint8)

    dst_pts = np.array([
        [0, 0],
        [max_w - 1, 0],
        [max_w - 1, max_h - 1],
        [0, max_h - 1]
    ], dtype=np.float32)

    matrix = cv2.getPerspectiveTransform(pts, dst_pts)
    warped = cv2.warpPerspective(
        image,
        matrix,
        (max_w, max_h),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_REPLICATE
    )

    # Apply manual rotation offset (0, 90, 180, 270)
    rot = rotation_offset % 360
    if rot == 90:
        warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)
    elif rot == 180:
        warped = cv2.rotate(warped, cv2.ROTATE_180)
    elif rot == 270:
        warped = cv2.rotate(warped, cv2.ROTATE_90_COUNTERCLOCKWISE)

    return warped
