from __future__ import annotations

import unicodedata


def alphabetical_key(value: str) -> tuple[str, str, str]:
    normalized = unicodedata.normalize("NFC", value).casefold()
    # Accents share their base letter; Spanish ñ follows the other n words.
    folded = "".join(char for char in unicodedata.normalize("NFD", normalized.replace("ñ", "n~")) if not unicodedata.combining(char))
    return folded, normalized, value
