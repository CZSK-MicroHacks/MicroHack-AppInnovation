"""Shared identity and category normalization primitives."""

from __future__ import annotations

import re
import unicodedata
from uuid import UUID

_APOSTROPHES = {"'", "\u2019"}
_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")


def category_slug(value: str) -> str:
    """Normalize a category name with the frozen ``category-slug-v1`` algorithm."""
    normalized = unicodedata.normalize("NFKD", value.strip()).lower()
    characters = (
        character
        for character in normalized
        if not unicodedata.category(character).startswith("M")
        and character not in _APOSTROPHES
    )
    return _NON_ALPHANUMERIC.sub("-", "".join(characters)).strip("-")


def identity_is_valid(product_id: str, filename: str) -> bool:
    """Return whether a product ID and image filename satisfy the identity contract."""
    try:
        parsed = UUID(product_id)
    except ValueError:
        return False
    canonical = str(parsed)
    return product_id == canonical and filename == f"{canonical}.png"
