"""Background job: hand document -> lines -> OCR -> word crops -> word_samples -> profile."""

import logging
import threading
import uuid
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from hwai import storage
from hwai.db import new_session
from hwai.hand.ocr import OcrEngine, get_ocr
from hwai.hand.profile import rebuild_profile
from hwai.hand.segment import BBox, deskew_page, find_lines, split_words, to_gray
from hwai.models import Hand, HandDocument, WordSample
from hwai.pdfio import page_images

log = logging.getLogger(__name__)
_lock = threading.Lock()


def quality_score(crop_gray: np.ndarray) -> float:
    """0..1 from ink contrast, stroke clarity (ink share, edge sharpness) and aspect sanity."""
    h, w = crop_gray.shape
    if h < 9 or w < 9:
        return 0.0
    _, otsu = cv2.threshold(crop_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink = otsu > 0
    share = float(ink.mean())
    if ink.sum() == 0 or share > 0.8:
        return 0.0
    contrast = (float(crop_gray[~ink].mean()) - float(crop_gray[ink].mean())) / 255.0
    contrast_s = min(1.0, max(0.0, contrast / 0.6))
    clarity_s = 1.0 if 0.03 <= share <= 0.5 else 0.4
    lap = float(np.abs(cv2.Laplacian(crop_gray, cv2.CV_32F)).mean())
    sharp_s = min(1.0, lap / 8.0)
    aspect = w / h
    aspect_s = 1.0 if 0.25 <= aspect <= 12 else 0.2
    return round(0.4 * contrast_s + 0.2 * clarity_s + 0.2 * sharp_s + 0.2 * aspect_s, 4)


def _crop(img: Image.Image, box: BBox, dx: int, dy: int) -> Image.Image:
    return img.crop((box.x0 + dx, box.y0 + dy, box.x1 + dx, box.y1 + dy))


def extract_words(page: Image.Image, ocr: OcrEngine) -> list[tuple[str, float, Image.Image]]:
    """(text, ocr_confidence, crop) for every OCR word aligned to a word box on the page."""
    page = deskew_page(page.convert("L"))
    ocr.start_page()
    out: list[tuple[str, float, Image.Image]] = []
    for line in find_lines(page):
        line_img = page.crop((line.x0, line.y0, line.x1, line.y1))
        result = ocr.read_line(line_img)
        words = result.text.split()
        if not words:
            continue
        boxes = split_words(line_img)
        if len(boxes) != len(words):
            boxes = split_words(line_img, n_words=len(words))
        if len(boxes) != len(words):
            continue  # cannot align safely: drop the line
        for word, box in zip(words, boxes, strict=True):
            out.append((word, result.confidence, _crop(line_img, box, 0, 0)))
    return out


def ingest_pages(
    db: Session, hand: Hand, doc: HandDocument, pages: list[Image.Image], ocr: OcrEngine
) -> int:
    added = 0
    for page in pages:
        for text, conf, crop in extract_words(page, ocr):
            if crop.width <= 8 or crop.height <= 8:
                continue
            quality = quality_score(to_gray(crop))
            if quality <= 0.0:
                continue
            rel = f"{hand.user_id}/crops/{uuid.uuid4().hex}.png"
            path = storage.absolute_path(rel)
            path.parent.mkdir(parents=True, exist_ok=True)
            crop.save(path)
            db.add(
                WordSample(
                    hand_id=hand.id,
                    document_id=doc.id,
                    text=text,
                    crop_path=rel,
                    width=crop.width,
                    height=crop.height,
                    ocr_confidence=conf,
                    quality_score=quality,
                )
            )
            added += 1
    db.commit()
    return added


def ingest_document(document_id: str) -> None:
    """Entry point for the FastAPI background task. Never raises."""
    with _lock, new_session() as db:
        doc = db.get(HandDocument, document_id)
        if doc is None:
            return
        hand = db.get(Hand, doc.hand_id)
        if hand is None:
            return
        try:
            doc.status = "processing"
            hand.status = "learning"
            db.commit()
            pages = page_images(Path(storage.absolute_path(doc.file_path)))
            added = ingest_pages(db, hand, doc, pages, get_ocr())
            doc.status = "done" if added else "failed"
            rebuild_profile(db, hand)
            db.commit()
        except Exception:
            log.exception("hand ingestion failed for document %s", document_id)
            db.rollback()
            doc = db.get(HandDocument, document_id)
            hand = db.get(Hand, doc.hand_id) if doc else None
            if doc and hand:
                doc.status = "failed"
                hand.status = "failed"
                hand.status_reason = "processing_error"
                db.commit()
