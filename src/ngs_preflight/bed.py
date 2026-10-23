"""Tolerant BED parser that records everything the checks need to know about a file."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ngs_preflight.errors import PreflightError

HEADER_PREFIXES = ("track", "browser", "#")


@dataclass(frozen=True)
class Interval:
    contig: str
    start: int
    end: int
    name: str | None
    line: int
    extra: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParseProblem:
    line: int
    reason: str
    text: str


@dataclass
class BedFile:
    path: str
    intervals: list[Interval] = field(default_factory=list)
    problems: list[ParseProblem] = field(default_factory=list)
    header_lines: list[tuple[int, str]] = field(default_factory=list)
    blank_lines: int = 0
    has_bom: bool = False
    crlf_lines: list[int] = field(default_factory=list)
    space_delimited_lines: list[int] = field(default_factory=list)
    trailing_ws_lines: list[int] = field(default_factory=list)
    total_lines: int = 0
    max_columns: int = 3

    @property
    def has_names(self) -> bool:
        return any(iv.name is not None for iv in self.intervals)


def _clean_name(value: str) -> str | None:
    value = value.strip()
    return value or None


def parse_bed_text(data: bytes, path: str = "<memory>") -> BedFile:
    """Parse BED bytes. Never raises on bad content; problems are recorded instead."""
    bed = BedFile(path=path)
    if data.startswith(b"\xef\xbb\xbf"):
        bed.has_bom = True
        data = data[3:]
    text = data.decode("utf-8", errors="replace")
    raw_lines = text.split("\n")
    if raw_lines and raw_lines[-1] == "":
        raw_lines.pop()
    for number, raw in enumerate(raw_lines, 1):
        bed.total_lines += 1
        line = raw
        if line.endswith("\r"):
            bed.crlf_lines.append(number)
            line = line[:-1]
        stripped = line.strip()
        if not stripped:
            bed.blank_lines += 1
            continue
        if stripped.startswith(HEADER_PREFIXES):
            bed.header_lines.append((number, stripped))
            continue
        if line != line.rstrip():
            bed.trailing_ws_lines.append(number)
        fields = line.rstrip().split("\t")
        if len(fields) == 1 or (len(fields) < 3 and " " in line):
            spaced = line.split()
            if len(spaced) >= 3:
                bed.space_delimited_lines.append(number)
                fields = spaced
        if len(fields) < 3:
            bed.problems.append(
                ParseProblem(
                    number,
                    f"expected at least 3 tab-separated columns, found {len(fields)}",
                    stripped[:80],
                )
            )
            continue
        try:
            start, end = int(fields[1].strip()), int(fields[2].strip())
        except ValueError:
            bed.problems.append(
                ParseProblem(
                    number,
                    f"start and end must be whole numbers, found {fields[1]!r} and {fields[2]!r}",
                    stripped[:80],
                )
            )
            continue
        bed.max_columns = max(bed.max_columns, len(fields))
        name = _clean_name(fields[3]) if len(fields) >= 4 else None
        extra = tuple(f.strip() for f in fields[3:])
        bed.intervals.append(Interval(fields[0].strip(), start, end, name, number, extra))
    return bed


def read_bed(path: str | Path) -> BedFile:
    p = Path(path)
    if not p.is_file():
        raise PreflightError(f"BED file not found: {p}")
    try:
        data = p.read_bytes()
    except OSError as exc:
        raise PreflightError(f"cannot read BED file {p}: {exc}") from exc
    if p.suffix.lower() == ".gz" or data[:2] == b"\x1f\x8b":
        import gzip

        try:
            data = gzip.decompress(data)
        except (OSError, EOFError) as exc:
            raise PreflightError(
                f"{p} looks gzip-compressed but cannot be decompressed: {exc}"
            ) from exc
    return parse_bed_text(data, str(path))


def merge_intervals(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping and book-ended (start == previous end) spans."""
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def by_contig(intervals: list[Interval]) -> dict[str, list[Interval]]:
    groups: dict[str, list[Interval]] = {}
    for iv in intervals:
        groups.setdefault(iv.contig, []).append(iv)
    return groups
