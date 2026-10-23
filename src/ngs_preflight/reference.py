"""Load a reference's contig names and lengths from a ``.fai`` or ``.dict`` file."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ngs_preflight.errors import PreflightError

_SN = re.compile(r"SN:(\S+)")
_LN = re.compile(r"LN:(\d+)")


@dataclass(frozen=True)
class Reference:
    path: str
    lengths: dict[str, int]  # insertion-ordered: reference order
    source: str  # "fai" or "dict"

    @property
    def order(self) -> dict[str, int]:
        return {name: i for i, name in enumerate(self.lengths)}


def parse_fai(text: str) -> dict[str, int]:
    lengths: dict[str, int] = {}
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) < 2 or not fields[1].isdigit():
            raise PreflightError(f"line {n} is not a valid .fai record: {line[:60]!r}")
        lengths[fields[0]] = int(fields[1])
    return lengths


def parse_dict(text: str) -> dict[str, int]:
    lengths: dict[str, int] = {}
    for line in text.splitlines():
        if not line.startswith("@SQ"):
            continue
        sn, ln = _SN.search(line), _LN.search(line)
        if sn and ln:
            lengths[sn.group(1)] = int(ln.group(1))
    return lengths


def load_reference(path: str | Path) -> Reference:
    """Read a ``.fai`` or ``.dict``; for a FASTA path, use the ``.fai`` beside it."""
    p = Path(path)
    suffixes = p.suffixes
    if p.suffix.lower() in {".fa", ".fasta", ".fna"} or (
        len(suffixes) >= 2 and suffixes[-1] == ".gz" and suffixes[-2] in {".fa", ".fasta", ".fna"}
    ):
        fai = Path(str(p) + ".fai")
        if not fai.exists():
            raise PreflightError(
                f"{p} is a FASTA file but {fai.name} was not found next to it. "
                "Create it with 'samtools faidx' or pass the .fai or .dict file instead."
            )
        p = fai
    if not p.is_file():
        raise PreflightError(f"reference file not found: {p}")
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise PreflightError(f"cannot read reference file {p}: {exc}") from exc
    if p.suffix.lower() == ".dict":
        lengths, source = parse_dict(text), "dict"
    else:
        try:
            lengths, source = parse_fai(text), "fai"
        except PreflightError:
            lengths, source = parse_dict(text), "dict"
            if not lengths:
                raise
    if not lengths:
        raise PreflightError(f"no contigs found in {p}; expected a .fai or .dict file")
    return Reference(path=str(path), lengths=lengths, source=source)
