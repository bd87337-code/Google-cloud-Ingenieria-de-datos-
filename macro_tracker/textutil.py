"""Normalización de texto para búsquedas."""
from __future__ import annotations

import re
import unicodedata


def normalize_text(text: str | None) -> str:
    """Minúsculas, sin acentos (conserva la ñ como n) y con espacios colapsados."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.lower()).strip()
