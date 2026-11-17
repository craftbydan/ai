"""Style profile: the best, varied word crops of a user's own handwriting."""

import random
import re
from collections import defaultdict

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from hwai import storage
from hwai.db import new_session
from hwai.models import Hand, WordSample
from hwai.render.base import StyleRef

MAX_SAMPLES = 150
MIN_USABLE_SAMPLES = 20
MIN_QUALITY = 0.35
MAX_PER_WORD = 4

REASONS: dict[str, str] = {
    "not_enough_ink": (
        "We could not find enough clear handwriting. Please upload a sharp, well-lit page "
        "with several lines of your own writing."
    ),
    "processing_error": "Something went wrong while reading your handwriting. Please try again.",
}


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def choose_samples(samples: list[WordSample]) -> list[WordSample]:
    """Up to MAX_SAMPLES usable samples, best quality first, with at most MAX_PER_WORD per word."""
    usable = [s for s in samples if (s.quality_score or 0.0) >= MIN_QUALITY and _key(s.text)]
    usable.sort(key=lambda s: (-(s.quality_score or 0.0), s.id))
    per_word: dict[str, int] = defaultdict(int)
    chosen: list[WordSample] = []
    for s in usable:
        k = _key(s.text)
        if per_word[k] < MAX_PER_WORD and len(chosen) < MAX_SAMPLES:
            per_word[k] += 1
            chosen.append(s)
    return chosen


def rebuild_profile(db: Session, hand: Hand) -> int:
    """Re-pick the profile from all samples, prune the rest, set hand status. Returns count."""
    samples = list(db.scalars(select(WordSample).where(WordSample.hand_id == hand.id)))
    chosen = choose_samples(samples)
    keep = {s.id for s in chosen}
    for s in samples:
        if s.id not in keep:
            storage.delete_file(s.crop_path)
            db.delete(s)
    if len(chosen) >= MIN_USABLE_SAMPLES:
        hand.status = "ready"
        hand.status_reason = None
    else:
        hand.status = "failed"
        hand.status_reason = "not_enough_ink"
    db.commit()
    return len(chosen)


def style_refs_for(
    hand_id: str, k: int = 8, seed: int = 0, db: Session | None = None
) -> list[StyleRef]:
    """`k` style references picked at random (seeded) from the hand's profile."""
    own = db is None
    session = db or new_session()
    try:
        samples = list(
            session.scalars(
                select(WordSample).where(WordSample.hand_id == hand_id).order_by(WordSample.id)
            )
        )
        rng = random.Random(seed)
        rng.shuffle(samples)
        refs: list[StyleRef] = []
        for s in samples[: max(0, k)]:
            with Image.open(storage.absolute_path(s.crop_path)) as im:
                refs.append(StyleRef(text=s.text, image=im.convert("RGBA")))
        return refs
    finally:
        if own:
            session.close()
