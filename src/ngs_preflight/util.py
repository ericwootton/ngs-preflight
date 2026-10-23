"""Small text helpers shared by checks and reports."""

from __future__ import annotations

from collections.abc import Iterable, Sequence


def plural(n: int, singular: str, plural_form: str | None = None) -> str:
    """``plural(1, 'line')`` -> ``'1 line'``; ``plural(3, 'line')`` -> ``'3 lines'``."""
    word = singular if n == 1 else (plural_form or singular + "s")
    return f"{n:,} {word}"


def quote_list(items: Iterable[str], limit: int = 6) -> str:
    """``"a", "b", "c" and 4 more`` style list for messages."""
    seq: Sequence[str] = list(items)
    shown = ", ".join(f'"{x}"' for x in seq[:limit])
    extra = len(seq) - limit
    return shown + (f" and {extra} more" if extra > 0 else "")


def verb(n: int, singular: str, plural_form: str) -> str:
    """Pick the verb form that agrees with a count."""
    return singular if n == 1 else plural_form


def cap(text: str) -> str:
    """Upper-case the first character only."""
    return text[:1].upper() + text[1:]


def bp(n: int) -> str:
    return f"{n:,} bp"


def mb(n: int) -> str:
    return f"{n / 1_000_000:.2f} Mb"
