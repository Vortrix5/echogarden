"""OCR quality detection — determine whether OCR output is meaningful.

For a photo image to be considered "text-bearing", the OCR output must
clear several hurdles so that noise from non-text images (e.g. a photo
of a house or landscape) is correctly rejected.
"""

from __future__ import annotations

import re

_OCR_FAILURE_TOKENS = {
    "error", "tesseract", "exception", "could not", "failed",
    "ocr error", "ocr timeout", "not installed", "file not found",
}

_REPEATED_CHAR_RE = re.compile(r"(.)\1{4,}")  # same char 5+ times
_WORD_RE = re.compile(r"[A-Za-z]{2,}")  # words: 2+ consecutive letters


def is_meaningful_ocr(
    text: str | None,
    *,
    min_chars: int = 30,
    min_words: int = 3,
    min_alpha_ratio: float = 0.30,
    avg_confidence: float | None = None,
    min_confidence: float = 40.0,
    max_garbage_ratio: float = 0.50,
) -> bool:
    """Return True only if OCR text looks like real, usable content.

    Checks (all must pass):
      1. Not None/empty/whitespace
      2. Length >= min_chars  (default 30)
      3. Word count >= min_words  (default 3, prevents short noise)
      4. avg_confidence >= min_confidence  (if provided; default 40)
      5. No OCR failure tokens
      6. Alpha ratio >= min_alpha_ratio  (default 0.30)
      7. Garbage ratio (non-alphanumeric, non-space / total) < max_garbage_ratio
      8. Not mostly repeated chars
    """
    if text is None:
        return False

    stripped = text.strip()
    if not stripped:
        return False

    if len(stripped) < min_chars:
        return False

    # Word-count gate — real text has words, OCR noise does not
    words = _WORD_RE.findall(stripped)
    if len(words) < min_words:
        return False

    # Confidence gate
    if avg_confidence is not None and avg_confidence < min_confidence:
        return False

    # Check for OCR failure tokens (case-insensitive)
    lower = stripped.lower()
    for token in _OCR_FAILURE_TOKENS:
        if token in lower:
            return False

    # Starts with error marker brackets
    if stripped.startswith("[") and any(
        stripped.startswith(f"[{t}") for t in ("OCR", "File", "Tesseract", "Error")
    ):
        return False

    # Alpha ratio
    alpha_count = sum(1 for c in stripped if c.isalpha())
    total = len(stripped)
    if total > 0 and (alpha_count / total) < min_alpha_ratio:
        return False

    # Garbage ratio — catch strings full of |, /, \, ~, etc.
    garbage_count = sum(
        1 for c in stripped if not c.isalnum() and not c.isspace()
    )
    if total > 0 and (garbage_count / total) > max_garbage_ratio:
        return False

    # Mostly repeated characters
    if _REPEATED_CHAR_RE.search(stripped):
        unique_chars = len(set(stripped))
        if unique_chars < 10:
            return False

    return True
