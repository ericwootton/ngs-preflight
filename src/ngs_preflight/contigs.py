"""Contig-name helpers: naming style, alt/decoy detection, human build detection."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

PRIMARY_RE = re.compile(r"^(?:chr)?(?:[0-9]{1,2}|X|Y|M|MT)$")
_PRIMARY_NUMERIC_SEX = re.compile(r"^(?:chr)?(?:[0-9]{1,2}|X|Y)$")

# Primary-assembly contig lengths, used only to recognise the human build.
GRCH38_LENGTHS: dict[str, int] = {
    "1": 248956422, "2": 242193529, "3": 198295559, "4": 190214555, "5": 181538259,
    "6": 170805979, "7": 159345973, "8": 145138636, "9": 138394717, "10": 133797422,
    "11": 135086622, "12": 133275309, "13": 114364328, "14": 107043718, "15": 101991189,
    "16": 90338345, "17": 83257441, "18": 80373285, "19": 58617616, "20": 64444167,
    "21": 46709983, "22": 50818468, "X": 156040895, "Y": 57227415,
}  # fmt: skip
GRCH37_LENGTHS: dict[str, int] = {
    "1": 249250621, "2": 243199373, "3": 198022430, "4": 191154276, "5": 180915260,
    "6": 171115067, "7": 159138663, "8": 146364022, "9": 141213431, "10": 135534747,
    "11": 135006516, "12": 133851895, "13": 115169878, "14": 107349540, "15": 102531392,
    "16": 90354753, "17": 81195210, "18": 78077248, "19": 59128983, "20": 63025520,
    "21": 48129895, "22": 51304566, "X": 155270560, "Y": 59373566,
}  # fmt: skip


def strip_chr(name: str) -> str:
    """Name without a leading ``chr`` (``chrM`` becomes ``MT``)."""
    if name == "chrM":
        return "MT"
    return name[3:] if name.startswith("chr") else name


def add_chr(name: str) -> str:
    """Name with a ``chr`` prefix added for primary contigs (``MT`` becomes ``chrM``)."""
    if name in {"MT", "M"}:
        return "chrM"
    if name.startswith("chr"):
        return name
    if _PRIMARY_NUMERIC_SEX.match(name):
        return "chr" + name
    return name


def is_primary(name: str) -> bool:
    return bool(PRIMARY_RE.match(name))


def is_alt_like(name: str) -> bool:
    """True for anything that is not a primary chromosome: alt, decoy, unplaced, HLA, viral."""
    return not is_primary(name)


def naming_style(names: Iterable[str]) -> str:
    """Classify primary contigs as ``chr`` style, ``plain`` style, ``mixed`` or ``unknown``."""
    chr_style = plain = 0
    for name in names:
        if not is_primary(name):
            continue
        if name.startswith("chr"):
            chr_style += 1
        else:
            plain += 1
    if chr_style and plain:
        return "mixed"
    if chr_style:
        return "chr"
    if plain:
        return "plain"
    return "unknown"


def suggest_rename(name: str, known: Iterable[str]) -> str | None:
    """If toggling the ``chr`` prefix turns ``name`` into a known contig, return that name."""
    known_set = set(known)
    for candidate in (add_chr(name), strip_chr(name)):
        if candidate != name and candidate in known_set:
            return candidate
    return None


def detect_build(lengths: Mapping[str, int]) -> str | None:
    """Return ``GRCh38``/``GRCh37`` if primary contig lengths clearly match one build."""
    hits38 = hits37 = 0
    for name, length in lengths.items():
        key = strip_chr(name)
        if GRCH38_LENGTHS.get(key) == length:
            hits38 += 1
        if GRCH37_LENGTHS.get(key) == length:
            hits37 += 1
    if hits38 >= 3 and hits38 > hits37:
        return "GRCh38"
    if hits37 >= 3 and hits37 > hits38:
        return "GRCh37"
    return None
