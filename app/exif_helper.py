"""
EXIF and metadata helper for embedding photo dates and information.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional
import cv2
import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo
import piexif


def format_exif_date(date_str: str) -> str:
    """
    Converts various date formats (e.g. 'YYYY-MM-DD', 'YYYY/MM/DD', 'YYYY')
    into standard EXIF date format 'YYYY:MM:DD HH:MM:SS'.
    """
    cleaned = date_str.strip().replace("/", "-").replace(".", "-")
    parts = cleaned.split("-")
    
    year = "2000"
    month = "01"
    day = "01"

    if len(parts) >= 1 and parts[0].isdigit():
        year = parts[0].zfill(4)
    if len(parts) >= 2 and parts[1].isdigit():
        month = parts[1].zfill(2)
    if len(parts) >= 3 and parts[2].isdigit():
        day = parts[2].zfill(2)

    return f"{year}:{month}:{day} 12:00:00"


def save_image_with_metadata(
    image_bgr: np.ndarray,
    output_path: Path | str,
    date_str: Optional[str] = None,
    quality: int = 95
) -> bool:
    """
    Saves a cropped BGR image to disk, embedding the date into EXIF or PNG metadata.
    """
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ext = out_path.suffix.lower()

    # Convert BGR (OpenCV) to RGB (Pillow)
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(image_rgb)

    if ext in (".jpg", ".jpeg"):
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}
        if date_str:
            exif_date = format_exif_date(date_str).encode("utf-8")
            exif_dict["0th"][piexif.ImageIFD.DateTime] = exif_date
            exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = exif_date
            exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = exif_date

        exif_bytes = piexif.dump(exif_dict)
        pil_img.save(out_path, "JPEG", quality=quality, exif=exif_bytes)
        return True

    elif ext == ".png":
        png_info = PngInfo()
        if date_str:
            png_info.add_text("Creation Time", date_str)
            png_info.add_text("Date", date_str)
        pil_img.save(out_path, "PNG", pnginfo=png_info)
        return True

    elif ext in (".tif", ".tiff"):
        pil_img.save(out_path, "TIFF")
        return True

    else:
        # Fallback to standard save
        cv2.imwrite(str(out_path), image_bgr)
        return True

