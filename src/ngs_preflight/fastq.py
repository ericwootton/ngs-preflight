"""Minimal FASTQ helpers: read the first record names and pair-name logic."""

from __future__ import annotations

import gzip
import re
from pathlib import Path

_R_TOKEN = re.compile(r"(?<![A-Za-z0-9])(R?)([12])(?![0-9])")
_SUFFIX = re.compile(r"(?i)(\.f(?:ast)?q(?:\.gz)?|\.bam|\.cram)$")


def read_names(path: str | Path, n: int = 100) -> list[str]:
    """First ``n`` read names (first token of the header line, without a trailing /1 or /2)."""
    p = Path(path)
    opener = gzip.open if p.suffix.lower() in {".gz", ".bgz"} else open
    names: list[str] = []
    with opener(p, "rt", encoding="utf-8", errors="replace") as handle:
        for i, line in enumerate(handle):
            if i % 4 == 0:
                if not line.startswith("@"):
                    break
                token = line[1:].split()[0] if line[1:].split() else ""
                names.append(re.sub(r"/[12]$", "", token))
                if len(names) >= n:
                    break
    return names


def mate_marker(filename: str) -> tuple[str, str] | None:
    """Return (stem-with-placeholder, mate) such as ('S1_R#_001', '1'), or None if no marker.

    Recognises _R1/_R2, .R1/.R2, _1/_2 and similar before the FASTQ extension.
    """
    base = Path(filename).name
    stem = _SUFFIX.sub("", base)
    matches = list(_R_TOKEN.finditer(stem))
    if not matches:
        return None
    with_r = [x for x in matches if x.group(1)]  # prefer R1/R2 over a bare 1 or 2
    m = (with_r or matches)[-1]
    return stem[: m.start()] + "R#" + stem[m.end() :], m.group(2)
