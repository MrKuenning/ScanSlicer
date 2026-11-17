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

    # Normalize angle into (-45, 45]; swap w and h whenever rotating by 90 degrees
    while angle > 45.0:
        angle -= 90.0
        w, h = h, w
    while angle <= -45.0:
        angle += 90.0
        w, h = h, w

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


def _contours_to_candidates(contours, min_area: float, max_area: float):
    """Converts external contours into validated, angle-snapped rectangle candidates."""
    candidates = []
    oversized = []
    for c in contours:
        hull_area = cv2.contourArea(cv2.convexHull(c))
        if hull_area < min_area:
            continue

        rect = cv2.minAreaRect(c)
        snapped_rect = snap_rect_angle(rect, snap_threshold=3.0)
        (cx, cy), (rw, rh), angle = snapped_rect
        box_area = float(rw * rh)

        if box_area < min_area:
            continue
        if box_area > max_area:
            oversized.append(c)
            continue

        # Reject slivers with extreme aspect ratio
        if min(rw, rh) < 25:
            continue
        aspect = max(rw, rh) / (min(rw, rh) + 1e-5)
        if aspect > 12:
            continue

        candidates.append({
            "area": box_area,
            "rect": snapped_rect,
        })
    return candidates, oversized


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

    # 2. Sample outer borders (1% strip) to estimate scanner platen background color & noise floor
    border_width = max(4, int(min(wh, ww) * 0.01))
    borders = np.concatenate([
        work_img[0:border_width, :].reshape(-1, 3),
        work_img[-border_width:, :].reshape(-1, 3),
        work_img[:, 0:border_width].reshape(-1, 3),
        work_img[:, -border_width:].reshape(-1, 3)
    ], axis=0)
    bg_color = np.median(borders, axis=0)

    # 3. Method A: Perceptual LAB Color distance anchored to platen background noise
    work_lab = cv2.cvtColor(work_img, cv2.COLOR_BGR2LAB)
    bg_lab = cv2.cvtColor(np.uint8([[bg_color]]), cv2.COLOR_BGR2LAB)[0, 0]
    diff_lab = np.linalg.norm(work_lab.astype(np.float32) - bg_lab.astype(np.float32), axis=2)

    borders_lab = cv2.cvtColor(borders.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_BGR2LAB).reshape(-1, 3)
    border_diffs = np.linalg.norm(borders_lab.astype(np.float32) - bg_lab.astype(np.float32), axis=1)

    # If the outer border is non-uniform (photos touch the scan edge), fall back to low-gradient
    # bright/uniform pixels (e.g. white scanner gutters) for background estimation.
    if float(np.percentile(border_diffs, 70)) > 12.0:
        l_chan_tmp = work_lab[:, :, 0]
        bright_mask = l_chan_tmp >= np.percentile(l_chan_tmp, 90)
        if np.any(bright_mask):
            bg_color = np.median(work_img[bright_mask], axis=0)
            bg_lab = cv2.cvtColor(np.uint8([[bg_color]]), cv2.COLOR_BGR2LAB)[0, 0]
            diff_lab = np.linalg.norm(work_lab.astype(np.float32) - bg_lab.astype(np.float32), axis=2)
            bg_noise = 3.0
        else:
            bg_noise = 6.0
    else:
        bg_noise = float(np.clip(np.percentile(border_diffs, 70), 1.5, 10.0))

    # Sensitivity mapping (1..100):
    # Higher sensitivity detects subtler paper borders and bright/light-toned photo regions.
    # Clamped above the measured platen noise floor to avoid background speckles.
    base_thresh = 20.0 - (sensitivity / 100.0) * 15.0
    thresh_val = max(base_thresh, bg_noise * 2.2)
    mask_diff = (diff_lab > thresh_val).astype(np.uint8) * 255

    # 4. Method B: Bilateral-filtered lightness edge detection (catches white/off-white photo borders)
    l_chan = work_lab[:, :, 0]
    blurred_l = cv2.bilateralFilter(l_chan, 7, 40, 40)
    canny_low = int(max(8, 40 - sensitivity * 0.28))
    canny_high = canny_low * 3
    edges = cv2.Canny(blurred_l, canny_low, canny_high)

    # Combine distance mask and edges
    combined_mask = cv2.bitwise_or(mask_diff, edges)

    # 5. Small morphological closing (3x3) to seal 1-2px border gaps without bridging narrow gutters
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    closed = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel)

    # 6. Find external contours so inner details/frames never replace the outer photo boundary
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_area = total_area * min_area_ratio * (scale * scale)
    max_area = total_area * max_area_ratio * (scale * scale)

    raw_candidates, oversized = _contours_to_candidates(contours, min_area, max_area)

    # If a giant contour (> max_area) swallowed multiple photos across a narrow gutter/border,
    # split it using mask_diff opened by 3x3 (severs thin edge bridges).
    if oversized:
        opened_diff = cv2.morphologyEx(mask_diff, cv2.MORPH_OPEN, kernel)
        for big_c in oversized:
            bx, by, bw, bh = cv2.boundingRect(big_c)
            sub_mask = opened_diff[by:by + bh, bx:bx + bw]
            sub_contours, _ = cv2.findContours(sub_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            shifted = [sc + np.array([[[bx, by]]], dtype=sc.dtype) for sc in sub_contours]
            sub_cands, _ = _contours_to_candidates(shifted, min_area, max_area)
            raw_candidates.extend(sub_cands)

    # 7. Non-Maximum Suppression: prefer larger complete photo boxes over overlapping fragments
    kept_rects = []
    raw_candidates.sort(key=lambda x: x["area"], reverse=True)

    for cand in raw_candidates:
        c_rect = cand["rect"]
        c_area = cand["area"]
        is_duplicate = False

        for k_rect, k_area in kept_rects:
            ret, pts = cv2.rotatedRectangleIntersection(c_rect, k_rect)
            if pts is not None and len(pts) >= 3:
                inter_area = cv2.contourArea(pts)
                min_a = min(c_area, k_area)
                # If overlap exceeds 35% of the smaller box, treat as duplicate/fragment
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
