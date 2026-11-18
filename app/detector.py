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


def snap_rect_angle(rect: Tuple[Tuple[float, float], Tuple[float, float], float], snap_threshold: float = 0.5):
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
        snapped_rect = snap_rect_angle(rect, snap_threshold=0.5)
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
            "contour": c,
        })
    return candidates, oversized


def _split_by_background_gutters(
    cand: dict,
    closed_mask: np.ndarray,
    mask_diff: np.ndarray,
    min_area: float,
    max_area: float,
    depth: int = 0
) -> List[dict]:
    """
    Splits a candidate whose bounding box contains a full-span background gutter
    (e.g. multiple photos touching along one outer edge with a gap between them).
    """
    if depth > 3:
        return [cand]

    c = cand["contour"]
    bx, by, bw, bh = cv2.boundingRect(c)
    if bw < 60 or bh < 60:
        return [cand]

    sub_diff = mask_diff[by:by + bh, bx:bx + bw]
    sub_closed = closed_mask[by:by + bh, bx:bx + bw].copy()

    # Find rows/cols where >= 85% of pixels are background (mask_diff == 0)
    row_bg = (sub_diff == 0).mean(axis=1)
    col_bg = (sub_diff == 0).mean(axis=0)

    y_lo, y_hi = max(4, int(bh * 0.12)), min(bh - 4, int(bh * 0.88))
    x_lo, x_hi = max(4, int(bw * 0.12)), min(bw - 4, int(bw * 0.88))

    best_y = int(np.argmax(row_bg[y_lo:y_hi]) + y_lo) if y_hi > y_lo else -1
    best_x = int(np.argmax(col_bg[x_lo:x_hi]) + x_lo) if x_hi > x_lo else -1

    best_y_val = float(row_bg[best_y]) if best_y >= 0 else 0.0
    best_x_val = float(col_bg[best_x]) if best_x >= 0 else 0.0

    if max(best_y_val, best_x_val) < 0.85:
        return [cand]

    if best_y_val >= best_x_val:
        # Clear a 3px band around the strongest horizontal gutter
        sub_closed[max(0, best_y - 1):min(bh, best_y + 2), :] = 0
    else:
        sub_closed[:, max(0, best_x - 1):min(bw, best_x + 2)] = 0

    sub_contours, _ = cv2.findContours(sub_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    shifted = [sc + np.array([[[bx, by]]], dtype=sc.dtype) for sc in sub_contours]
    split_cands, _ = _contours_to_candidates(shifted, min_area, max_area)

    if len(split_cands) < 2:
        return [cand]

    result = []
    for sc in split_cands:
        result.extend(_split_by_background_gutters(sc, closed_mask, mask_diff, min_area, max_area, depth + 1))
    return result


def _split_mounting_page(
    cand: dict,
    work_lab: np.ndarray,
    blurred_l: np.ndarray,
    thresh_val: float,
    min_area: float,
    max_area: float,
    total_work_area: float,
) -> List[dict]:
    """
    Detects when a large candidate (>= 20% of image) contains >= 2 solid photos
    merged by faint handwriting, tape, or page-edge Canny bridges, and re-segments
    it against the local flat page color using opened LAB distance (no Canny).
    """
    if cand["area"] < total_work_area * 0.20:
        return [cand]

    bx, by, bw, bh = cv2.boundingRect(cand["contour"])
    if bw < 80 or bh < 80:
        return [cand]

    sub_lab = work_lab[by:by + bh, bx:bx + bw]
    sub_l = blurred_l[by:by + bh, bx:bx + bw]

    # Estimate local uniform page color from low-gradient, bright-ish pixels
    gx = cv2.Sobel(sub_l, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(sub_l, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = np.hypot(gx, gy)
    flat_mask = (grad_mag < 12.0) & (sub_l >= 160)
    if float(flat_mask.mean()) < 0.20:
        return [cand]

    local_bg_lab = np.median(sub_lab[flat_mask], axis=0).astype(np.float32)
    local_diff = np.linalg.norm(sub_lab.astype(np.float32) - local_bg_lab, axis=2)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    strict_thresh = max(thresh_val * 1.4, 18.0)
    local_mask = (local_diff > strict_thresh).astype(np.uint8) * 255
    local_opened = cv2.morphologyEx(local_mask, cv2.MORPH_OPEN, kernel)

    sub_contours, _ = cv2.findContours(local_opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    shifted = [sc + np.array([[[bx, by]]], dtype=sc.dtype) for sc in sub_contours]
    sub_cands, _ = _contours_to_candidates(shifted, min_area, max_area)

    # Filter out hollow L-shaped page-border artifacts (real photos are >= 30% filled)
    solid_cands = [
        sc for sc in sub_cands
        if (cv2.contourArea(sc["contour"]) / max(sc["area"], 1.0)) >= 0.30
    ]

    if len(solid_cands) >= 2:
        return solid_cands
    return [cand]


def _split_oversized_contour(
    big_c,
    sub_mask_src: np.ndarray,
    blurred_l: np.ndarray,
    diff_lab: np.ndarray,
    min_area: float,
    max_area: float,
    bx: int,
    by: int,
    bw: int,
    bh: int,
    depth: int = 0
):
    """
    Splits a merged multi-photo contour (narrow or zero gap) along its strongest
    horizontal/vertical dividing seam and returns validated crop candidates.
    """
    if depth > 2 or bw < 60 or bh < 60:
        return []

    sub_mask = sub_mask_src[by:by + bh, bx:bx + bw].copy()
    sub_l = blurred_l[by:by + bh, bx:bx + bw]
    sub_diff = diff_lab[by:by + bh, bx:bx + bw]

    grad_y = np.abs(cv2.Sobel(sub_l, cv2.CV_32F, 0, 1, ksize=3))
    grad_x = np.abs(cv2.Sobel(sub_l, cv2.CV_32F, 1, 0, ksize=3))

    best_orient = None
    best_pos = 0
    best_score = -1.0
    best_edge_frac = 0.0

    # Search horizontal seams
    y_start, y_end = max(4, int(bh * 0.15)), min(bh - 4, int(bh * 0.85))
    for y in range(y_start, y_end):
        e_frac = float((grad_y[y - 3:y + 4, :].max(axis=0) > 25.0).mean())
        g_frac = float((sub_diff[y - 3:y + 4, :].min(axis=0) < 25.0).mean())
        score = e_frac + 0.5 * g_frac
        if score > best_score:
            best_score = score
            best_orient = "h"
            best_pos = y
            best_edge_frac = e_frac

    # Search vertical seams
    x_start, x_end = max(4, int(bw * 0.15)), min(bw - 4, int(bw * 0.85))
    for x in range(x_start, x_end):
        e_frac = float((grad_x[:, x - 3:x + 4].max(axis=1) > 25.0).mean())
        g_frac = float((sub_diff[:, x - 3:x + 4].min(axis=1) < 25.0).mean())
        score = e_frac + 0.5 * g_frac
        if score > best_score:
            best_score = score
            best_orient = "v"
            best_pos = x
            best_edge_frac = e_frac

    if best_orient is None or best_edge_frac < 0.65:
        return []

    if best_orient == "h":
        sub_mask[max(0, best_pos - 2):min(bh, best_pos + 3), :] = 0
    else:
        sub_mask[:, max(0, best_pos - 2):min(bw, best_pos + 3)] = 0

    sub_contours, _ = cv2.findContours(sub_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    shifted = [sc + np.array([[[bx, by]]], dtype=sc.dtype) for sc in sub_contours]
    cands, still_big = _contours_to_candidates(shifted, min_area, max_area)

    for sc in still_big:
        sx, sy, sw, sh = cv2.boundingRect(sc)
        cands.extend(_split_oversized_contour(
            sc, sub_mask_src, blurred_l, diff_lab, min_area, max_area,
            sx, sy, sw, sh, depth=depth + 1
        ))

    return cands


def inset_corners(corners: np.ndarray, inset_px: float) -> np.ndarray:
    """
    Moves all 4 edges of a [TL, TR, BR, BL] quadrilateral inward by inset_px pixels
    to cleanly trim edge slivers.
    """
    if inset_px <= 0:
        return corners

    pts = order_corners(corners).copy()
    tl, tr, br, bl = pts

    top_vec = tr - tl
    left_vec = bl - tl
    w_len = float(np.linalg.norm(top_vec))
    h_len = float(np.linalg.norm(left_vec))
    if w_len < 1e-4 or h_len < 1e-4:
        return pts

    # Clamp inset so the box never collapses or inverts
    d = min(float(inset_px), w_len * 0.25, h_len * 0.25)
    u = top_vec / w_len   # left -> right
    v = left_vec / h_len  # top -> bottom

    return np.array([
        tl + d * u + d * v,
        tr - d * u + d * v,
        br - d * u - d * v,
        bl + d * u - d * v,
    ], dtype=np.float32)


def _trim_white_edge_slivers(
    corners: np.ndarray,
    work_lab: np.ndarray,
    diff_lab: np.ndarray,
    thresh_val: float,
    scale: float,
    max_trim_work_px: int = 20
) -> np.ndarray:
    """
    Walks each of the 4 edges inward (in work_img space) while >= 75% of the edge
    consists of white/platen background pixels, eliminating residual white shims.
    """
    wh, ww = work_lab.shape[:2]
    pts = order_corners(corners).copy() * scale

    for _ in range(max_trim_work_px):
        tl, tr, br, bl = pts
        w_vec = tr - tl
        h_vec = bl - tl
        w_len = float(np.linalg.norm(w_vec))
        h_len = float(np.linalg.norm(h_vec))
        if w_len < 40.0 or h_len < 40.0:
            break

        u = w_vec / w_len
        v = h_vec / h_len
        moved = False

        def _is_edge_white(p0: np.ndarray, p1: np.ndarray) -> bool:
            ts = np.linspace(0.1, 0.9, 25)
            xs = np.clip(np.round(p0[0] + ts * (p1[0] - p0[0])).astype(int), 0, ww - 1)
            ys = np.clip(np.round(p0[1] + ts * (p1[1] - p0[1])).astype(int), 0, wh - 1)
            l_vals = work_lab[ys, xs, 0]
            a_vals = np.abs(work_lab[ys, xs, 1].astype(np.float32) - 128.0)
            b_vals = np.abs(work_lab[ys, xs, 2].astype(np.float32) - 128.0)
            d_vals = diff_lab[ys, xs]
            white_or_bg = ((l_vals >= 232) & (a_vals <= 12.0) & (b_vals <= 12.0)) | (d_vals <= thresh_val)
            return float(white_or_bg.mean()) >= 0.75

        if _is_edge_white(tl, tr):
            pts[0] += v
            pts[1] += v
            moved = True
        if _is_edge_white(bl, br):
            pts[2] -= v
            pts[3] -= v
            moved = True
        if _is_edge_white(tl, bl):
            pts[0] += u
            pts[3] += u
            moved = True
        if _is_edge_white(tr, br):
            pts[1] -= u
            pts[2] -= u
            moved = True

        if not moved:
            break

    return (pts / scale).astype(np.float32)


def detect_scanner_photos(
    image: np.ndarray,
    sensitivity: int = 50,
    min_area_ratio: float = 0.015,
    max_area_ratio: float = 0.90,
    edge_inset: int = 3
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

    # If a giant contour (> max_area) swallowed multiple photos across a narrow or zero gutter,
    # first try mask_diff opened by 3x3; if still merged, split along the strongest dividing seam.
    if oversized:
        opened_diff = cv2.morphologyEx(mask_diff, cv2.MORPH_OPEN, kernel)
        for big_c in oversized:
            bx, by, bw, bh = cv2.boundingRect(big_c)
            sub_mask = opened_diff[by:by + bh, bx:bx + bw]
            sub_contours, _ = cv2.findContours(sub_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            shifted = [sc + np.array([[[bx, by]]], dtype=sc.dtype) for sc in sub_contours]
            sub_cands, still_big = _contours_to_candidates(shifted, min_area, max_area)
            if len(sub_cands) >= 2 and not still_big:
                raw_candidates.extend(sub_cands)
            else:
                seam_cands = _split_oversized_contour(
                    big_c, closed, blurred_l, diff_lab, min_area, max_area, bx, by, bw, bh
                )
                raw_candidates.extend(seam_cands if seam_cands else sub_cands)

    # Split any remaining candidates that contain a full-span background gutter
    # (e.g. stacked photos touching along a single outer scan edge), or are mounting/album pages.
    split_candidates = []
    for cand in raw_candidates:
        for sc in _split_by_background_gutters(cand, closed, mask_diff, min_area, max_area):
            split_candidates.extend(
                _split_mounting_page(
                    sc, work_lab, blurred_l, thresh_val,
                    min_area, max_area, float(wh * ww)
                )
            )
    raw_candidates = split_candidates

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

        # Get guaranteed 90-degree corners, trim residual white border shims, then apply edge_inset
        corners = get_rect_corners(orig_rect)
        corners = _trim_white_edge_slivers(corners, work_lab, diff_lab, thresh_val, scale)
        if edge_inset > 0:
            corners = inset_corners(corners, float(edge_inset))
        orig_area = float(
            np.linalg.norm(corners[1] - corners[0]) * np.linalg.norm(corners[3] - corners[0])
        )

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
