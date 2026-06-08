from __future__ import annotations

import unicodedata



def normalize_surname(name: str | None) -> str:
    """Fold to a comparable key: strip diacritics, lowercase, keep only letters."""
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "".join(c for c in ascii_only.lower() if c.isalpha())
