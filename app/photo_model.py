"""
Photo data model representing detected and user-edited photo crops.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Tuple
import numpy as np


@dataclass
class PhotoModel:
    id: int
    corners: np.ndarray  # (4, 2) float32 [TL, TR, BR, BL] in image coordinates
    angle: float = 0.0   # Detected angle in degrees
    rotation_offset: int = 0  # Additional 0, 90, 180, 270 degree rotation
    date_str: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    caption: str = ""
    is_selected: bool = False
    lock_rectangular: bool = True

    @property
    def total_rotation(self) -> float:
        """Total rotation angle including manual 90-degree offsets."""
        return (self.angle + self.rotation_offset) % 360

    @property
    def center(self) -> Tuple[float, float]:
        """Center point of the crop box."""
        c = self.corners.mean(axis=0)
        return float(c[0]), float(c[1])

    @property
    def dimensions(self) -> Tuple[int, int]:
        """Approximate pixel dimensions (width, height) after deskewing."""
        tl, tr, br, bl = self.corners
        w1 = np.linalg.norm(tr - tl)
        w2 = np.linalg.norm(br - bl)
        h1 = np.linalg.norm(br - tr)
        h2 = np.linalg.norm(bl - tl)
        w = int(round(max(w1, w2)))
        h = int(round(max(h1, h2)))
        if self.rotation_offset in (90, 270):
            return h, w
        return w, h
