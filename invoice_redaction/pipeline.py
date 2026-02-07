import hashlib
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np
from langdetect import DetectorFactory, detect
from paddleocr import PaddleOCR
from pdf2image import convert_from_path
from PIL import Image, ImageDraw

DetectorFactory.seed = 42

SUPPORTED_EXTS = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"}
DPI = 300
MAX_PAGES = 200

OUT_IMG_DIR = Path("out/redacted_images")
REPORT_PATH = Path("out/pii_report.jsonl")

for path in [OUT_IMG_DIR, REPORT_PATH.parent]:
    path.mkdir(parents=True, exist_ok=True)

EMAIL_REGEX = re.compile(r"(?i)[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}")
PHONE_REGEX = re.compile(r"(?:\+?91[-\s]?)?[6-9]\d{9}")

USE_GPU = os.environ.get("USE_GPU", "true").lower() == "true"
PADDLE_OCR = PaddleOCR(lang="en", use_gpu=USE_GPU, show_log=False)


def load_images(path: Path, dpi: int = DPI, max_pages: int = MAX_PAGES) -> List[Image.Image]:
    if path.suffix.lower() not in SUPPORTED_EXTS:
        raise ValueError(f"Unsupported file type: {path.suffix}")
    if path.suffix.lower() == ".pdf":
        return convert_from_path(str(path), dpi=dpi, first_page=1, last_page=max_pages)
    return [Image.open(path).convert("RGB")]


def preprocess_image(img: Image.Image) -> Image.Image:
    arr = np.array(img)
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    blurred = cv2.GaussianBlur(denoised, (3, 3), 0)
    return Image.fromarray(blurred)


def run_ocr(img: Image.Image) -> List[Dict[str, object]]:
    result = PADDLE_OCR.ocr(np.array(img), cls=True) or []
    lines: List[Dict[str, object]] = []
    for line in (result[0] if result else []):
        quad, (text, conf) = line
        lines.append({"bbox_quad": quad, "text": text, "conf": float(conf)})
    return lines


def detect_language(text: str) -> str:
    if not text.strip():
        return "en"
    try:
        return detect(text)
    except Exception:
        return "en"


def find_regex_pii(text: str) -> List[Dict[str, object]]:
    hits: List[Dict[str, object]] = []
    for match in EMAIL_REGEX.finditer(text):
        hits.append({"type": "EMAIL", "text": match.group(), "span": match.span()})
    for match in PHONE_REGEX.finditer(text):
        hits.append({"type": "PHONE", "text": match.group(), "span": match.span()})
    return hits


def bbox_from_quad(quad: List[List[float]]) -> Tuple[int, int, int, int]:
    xs = [pt[0] for pt in quad]
    ys = [pt[1] for pt in quad]
    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))


def collect_pii(lines: List[Dict[str, object]]):
    detections = []
    boxes = []
    for line in lines:
        hits = find_regex_pii(line["text"])
        if not hits:
            continue
        box = bbox_from_quad(line["bbox_quad"])
        boxes.append(box)
        for hit in hits:
            detections.append(
                {
                    "type": hit["type"],
                    "text_sample": hit["text"],
                    "bbox_xyxy": list(box),
                    "confidence": line["conf"],
                    "mask_applied": True,
                }
            )
    return detections, boxes


def apply_redactions(img: Image.Image, boxes, color=(0, 0, 0)):
    draw = ImageDraw.Draw(img)
    for (x1, y1, x2, y2) in boxes:
        draw.rectangle([x1, y1, x2, y2], fill=color)
    return img


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def save_page(img: Image.Image, base: Path, page_num: int) -> Path:
    out = OUT_IMG_DIR / f"{base.stem}_{page_num:03d}.png"
    img.save(out)
    return out


def append_report(entry: dict) -> None:
    with REPORT_PATH.open("a", encoding="utf8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def process_file(file_path: Path) -> List[Dict[str, object]]:
    images = load_images(file_path)
    file_hash = file_sha256(file_path)
    report_entries: List[Dict[str, object]] = []
    for page_num, img in enumerate(images, 1):
        pimg = preprocess_image(img)
        lines = run_ocr(pimg)
        text = "\n".join([line["text"] for line in lines])
        language = detect_language(text)
        detections, boxes = collect_pii(lines)
        redacted = apply_redactions(pimg.copy(), boxes)
        out_path = save_page(redacted, file_path, page_num)
        entry = {
            "file": str(file_path),
            "file_hash": file_hash,
            "page": page_num,
            "language": language,
            "detections": detections,
            "image_path": str(out_path),
        }
        append_report(entry)
        report_entries.append(entry)
    return report_entries
