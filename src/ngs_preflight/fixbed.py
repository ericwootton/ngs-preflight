"""``preflight fix-bed``: write a corrected copy of a BED file (never edits in place)."""

from __future__ import annotations

import gzip
import os
from dataclasses import dataclass, field
from pathlib import Path

from ngs_preflight.bed import BedFile, Interval, by_contig, merge_intervals, read_bed
from ngs_preflight.contigs import add_chr, strip_chr
from ngs_preflight.errors import PreflightError
from ngs_preflight.reference import Reference
from ngs_preflight.util import bp, plural


@dataclass
class FixOptions:
    add_chr: bool = False
    strip_chr: bool = False
    sort: bool = False
    merge: bool = False
    reference: Reference | None = None


@dataclass
class FixSummary:
    intervals_in: int = 0
    intervals_out: int = 0
    renamed: dict[tuple[str, str], int] = field(default_factory=dict)
    unchanged_contigs: list[str] = field(default_factory=list)
    sorted_applied: bool = False
    moved: int = 0
    merged_before: int = 0
    merged_after: int = 0
    bp_before: int = 0
    bp_after: int = 0
    cleanup: list[str] = field(default_factory=list)
    changed_samples: list[tuple[str, str]] = field(default_factory=list)

    def lines(self, src: str, dst: str) -> list[str]:
        out = [f"Wrote {dst} (your original {src} was not changed)."]
        out.append(f"  Intervals: {self.intervals_in:,} in, {self.intervals_out:,} out.")
        if self.renamed:
            total = sum(self.renamed.values())
            pairs = ", ".join(f"{a} -> {b} ({n:,})" for (a, b), n in list(self.renamed.items())[:8])
            more = len(self.renamed) - 8
            out.append(
                f"  Renamed chromosomes on {plural(total, 'interval')}: {pairs}"
                + (f" and {more} more" if more > 0 else "")
                + "."
            )
        if self.unchanged_contigs:
            out.append(
                "  Left unchanged (no matching 'chr' form): "
                + ", ".join(self.unchanged_contigs[:6])
                + (" ..." if len(self.unchanged_contigs) > 6 else "")
                + "."
            )
        if self.sorted_applied:
            out.append(f"  Sorted: {plural(self.moved, 'interval')} changed position.")
        if self.merged_before:
            out.append(
                f"  Merged: {self.merged_before:,} -> {self.merged_after:,} intervals; "
                f"{bp(self.bp_before)} -> {bp(self.bp_after)} (extra columns such as names are "
                "dropped when merging)."
            )
        if self.cleanup:
            out.append("  Formatting cleaned: " + "; ".join(self.cleanup) + ".")
        if self.changed_samples:
            out.append("  Examples of changed lines (before -> after):")
            for before, after in self.changed_samples:
                out.append(f"    {before}  ->  {after}")
        return out


def _format(iv: Interval) -> str:
    cols = [iv.contig, str(iv.start), str(iv.end), *iv.extra]
    return "\t".join(cols)


def _show(iv: Interval) -> str:
    return _format(iv).replace("\t", "<TAB>")


def fix_bed(bed: BedFile, opts: FixOptions) -> tuple[list[str], FixSummary]:
    """Return (output lines, summary). Raises PreflightError if the input is unusable."""
    if opts.add_chr and opts.strip_chr:
        raise PreflightError("--add-chr and --strip-chr cannot be used together")
    if bed.problems:
        first = bed.problems[0]
        raise PreflightError(
            f"{plural(len(bed.problems), 'line')} cannot be read as intervals (first: line "
            f"{first.line}: {first.reason}). Fix those lines by hand first; run 'preflight check' "
            "for details."
        )
    summary = FixSummary(intervals_in=len(bed.intervals))
    intervals = list(bed.intervals)
    if opts.merge and any(iv.start < 0 or iv.start >= iv.end for iv in intervals):
        raise PreflightError(
            "--merge needs every interval to have 0 <= start < end; fix those lines first "
            "(see BED002 in 'preflight check')."
        )

    rename = add_chr if opts.add_chr else strip_chr if opts.strip_chr else None
    if rename is not None:
        renamed: list[Interval] = []
        for iv in intervals:
            new = rename(iv.contig)
            if new != iv.contig:
                key = (iv.contig, new)
                summary.renamed[key] = summary.renamed.get(key, 0) + 1
                renamed.append(Interval(new, iv.start, iv.end, iv.name, iv.line, iv.extra))
            else:
                if iv.contig not in summary.unchanged_contigs and (
                    (opts.add_chr and not iv.contig.startswith("chr"))
                    or (opts.strip_chr and iv.contig.startswith("chr"))
                ):
                    summary.unchanged_contigs.append(iv.contig)
                renamed.append(iv)
        intervals = renamed

    original_order = list(intervals)
    if opts.sort or opts.merge:
        order = opts.reference.order if opts.reference else None

        def sort_key(pair: tuple[int, Interval]) -> tuple[int, str, int, int, int]:
            idx, iv = pair
            if order is not None:
                rank = order.get(iv.contig, len(order))
                return (rank, iv.contig if rank == len(order) else "", iv.start, iv.end, idx)
            return (0, iv.contig, iv.start, iv.end, idx)

        intervals = [iv for _, iv in sorted(enumerate(intervals), key=sort_key)]
        summary.sorted_applied = True
        summary.moved = sum(a is not b for a, b in zip(original_order, intervals, strict=True))

    if opts.merge:
        merged: list[Interval] = []
        summary.merged_before = len(intervals)
        summary.bp_before = sum(iv.end - iv.start for iv in intervals)
        groups = by_contig(intervals)
        for contig in dict.fromkeys(iv.contig for iv in intervals):
            for start, end in merge_intervals([(i.start, i.end) for i in groups[contig]]):
                merged.append(Interval(contig, start, end, None, 0))
        intervals = merged
        summary.merged_after = len(merged)
        summary.bp_after = sum(iv.end - iv.start for iv in merged)

    summary.intervals_out = len(intervals)
    lines = [text for _, text in bed.header_lines]
    lines.extend(_format(iv) for iv in intervals)

    if bed.has_bom:
        summary.cleanup.append("removed the byte-order mark")
    if bed.crlf_lines:
        summary.cleanup.append(f"converted {plural(len(bed.crlf_lines), 'line')} to Unix endings")
    if bed.space_delimited_lines:
        summary.cleanup.append(
            f"replaced spaces with tabs on {plural(len(bed.space_delimited_lines), 'line')}"
        )
    if bed.trailing_ws_lines:
        summary.cleanup.append(
            f"removed trailing whitespace on {plural(len(bed.trailing_ws_lines), 'line')}"
        )

    if not opts.merge:
        before_after = [
            (_show(o), _show(n))
            for o, n in zip(bed.intervals, intervals, strict=False)
            if (o.contig, o.start, o.end) != (n.contig, n.start, n.end)
        ]
        summary.changed_samples = before_after[:3]
    return lines, summary


def write_fixed(
    src: str | Path, dst: str | Path | None, opts: FixOptions, force: bool = False
) -> tuple[Path, FixSummary]:
    """Read ``src``, write the corrected copy to ``dst`` (default ``<name>.fixed.bed``)."""
    src_path = Path(src)
    bed = read_bed(src_path)
    if dst is None:
        dst_path = src_path.with_name(
            src_path.name.removesuffix(".gz").removesuffix(".bed") + ".fixed.bed"
        )
    else:
        dst_path = Path(dst)
    if dst_path.exists() and os.path.samefile(dst_path, src_path):
        raise PreflightError(
            "refusing to overwrite the input file: fix-bed always writes a new file. "
            "Choose a different --out name."
        )
    if dst_path.exists() and not force:
        raise PreflightError(f"{dst_path} already exists; choose another --out name or use --force")
    lines, summary = fix_bed(bed, opts)
    body = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    if dst_path.name.lower().endswith(".gz"):
        body = gzip.compress(body, mtime=0)
    dst_path.write_bytes(body)
    return dst_path, summary
