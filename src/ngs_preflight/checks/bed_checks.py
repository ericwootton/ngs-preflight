"""BED checks (BED001-BED011)."""

from __future__ import annotations

import statistics
from collections.abc import Iterator
from pathlib import PurePath

from ngs_preflight.bed import BedFile, Interval, by_contig, merge_intervals
from ngs_preflight.context import BedContext
from ngs_preflight.contigs import is_alt_like, naming_style, strip_chr, suggest_rename
from ngs_preflight.models import Severity
from ngs_preflight.registry import Hit, check
from ngs_preflight.util import bp, cap, mb, plural, quote_list, verb

SMALL_INTERVAL = 20
LARGE_INTERVAL = 1_000_000
ONE_BASED_MIN_EVIDENCE = 5


def valid_intervals(bed: BedFile) -> list[Interval]:
    """Intervals with 0 <= start < end (the only ones that have a meaningful size)."""
    return [iv for iv in bed.intervals if iv.start >= 0 and iv.start < iv.end]


def _name(path: str) -> str:
    return PurePath(path).name


@check(
    id="BED001",
    severity=Severity.ERROR,
    title="BED file can be read",
    message=(
        "{problem} Tools which read this file will stop running or silently skip the affected "
        "lines. This may result in the loss of some target regions."
    ),
    detail=(
        "Except for header lines, each line must contain at least 3 tab-separated columns, and "
        "columns 2 and 3 must contain integers. Lines beginning with 'track', 'browser', or '#' "
        "are permitted header lines and are included in the line count (see BED009). Blank lines "
        "are ignored. Gzip-compressed BED files are decompressed first."
    ),
    fix=(
        "Open the file and edit or delete the listed lines. Each line must contain a chromosome "
        "name, start position, and end position separated by tabs. Start and end positions must be "
        "integers."
    ),
    scope="bed",
)
def bed001(ctx: BedContext) -> Iterator[Hit]:
    bed = ctx.bed
    if bed.problems:
        first = bed.problems[0]
        n = len(bed.problems)
        examples = "; ".join(f"line {p.line}: {p.reason} ({p.text!r})" for p in bed.problems[:5])
        yield Hit(
            {
                "problem": (
                    f"{plural(n, 'line')} could not be read as an interval "
                    f"(for example line {first.line}: {first.reason})."
                )
            },
            technical=examples,
        )
    elif not bed.intervals:
        yield Hit(
            {"problem": "The BED file does not contain any intervals."},
            technical=f"{bed.total_lines} lines read, {len(bed.header_lines)} header lines.",
        )


@check(
    id="BED002",
    severity=Severity.ERROR,
    title="Start and end make sense",
    message=(
        "{count} {have} invalid coordinates (for example, line {line} starts at {start:,} and ends "
        "at {end:,}). Regions must start at 0 or greater and end after their start position. Empty "
        "regions or regions with reversed start and end positions are rejected or silently ignored "
        "by most tools."
    ),
    detail=("All intervals must satisfy 0 <= start < end. BED uses 0-based, half-open intervals."),
    fix=(
        "Check the start and end columns in the listed rows. If start and end have been swapped, "
        "restore their original order. You can remove empty regions where start and end are equal."
    ),
    scope="bed",
)
def bed002(ctx: BedContext) -> Iterator[Hit]:
    bad = [iv for iv in ctx.bed.intervals if iv.start < 0 or iv.start >= iv.end]
    if bad:
        first = bad[0]
        negative = sum(iv.start < 0 for iv in bad)
        empty = sum(iv.start == iv.end for iv in bad)
        backwards = sum(iv.start > iv.end for iv in bad)
        yield Hit(
            {
                "count": cap(plural(len(bad), "interval")),
                "have": "has" if len(bad) == 1 else "have",
                "line": first.line,
                "start": first.start,
                "end": first.end,
            },
            technical=(
                f"{negative} negative start, {empty} empty (start == end), {backwards} reversed "
                "(start > end). Lines: " + ", ".join(str(iv.line) for iv in bad[:10])
            ),
        )


def _rename_direction(missing: list[str], known: set[str]) -> tuple[str, str] | None:
    """('add-chr'|'strip-chr', example new name) if toggling fixes every missing contig."""
    directions: set[str] = set()
    example = ""
    for name in missing:
        new = suggest_rename(name, known)
        if new is None:
            return None
        adds = new.startswith("chr") and not name.startswith("chr")
        directions.add("add-chr" if adds else "strip-chr")
        example = example or new
    return (directions.pop(), example) if len(directions) == 1 else None


@check(
    id="BED003",
    severity=Severity.ERROR,
    title="Chromosome names exist in the reference",
    message=(
        "{summary} in the BED file cannot be found in the reference sequence: {contigs}. {hint} "
        "Tools will fail or skip these regions, so data you expect to be analysed would be "
        "missing."
    ),
    detail=(
        "All contig names in column 1 are checked against sequence names in the reference "
        ".fai/.dict using case-sensitive exact matching. If adding or removing the 'chr' prefix "
        "(including MT <-> chrM) resolves all unmatched names, the message states this and "
        "suggests running 'preflight fix-bed'."
    ),
    fix="{fix}",
    scope="bed",
    requires=("reference",),
)
def bed003(ctx: BedContext) -> Iterator[Hit]:
    assert ctx.reference is not None
    known = set(ctx.reference.lengths)
    counts: dict[str, int] = {}
    for iv in ctx.bed.intervals:
        if iv.contig not in known:
            counts[iv.contig] = counts.get(iv.contig, 0) + 1
    if not counts:
        return
    missing = list(counts)
    direction = _rename_direction(missing, known)
    fname = _name(ctx.bed.path)
    if direction:
        action, example = direction
        style = 'the "chr" prefix' if action == "add-chr" else "names without a chr prefix"
        hint = (
            f'The reference uses {style} (for example "{example}"), so this looks like a naming '
            "difference rather than missing data."
        )
        out = fname.rsplit(".", 1)[0] + ".fixed.bed"
        fix = (
            f"Run: preflight fix-bed --{action} {fname} --out {out}  (writes a corrected copy and "
            "leaves your original untouched)."
        )
    else:
        sample = [n for n in ctx.reference.lengths if not is_alt_like(n)][:4]
        hint = (
            "The reference spells its main chromosomes like " + quote_list(sample, 4) + "."
            if sample
            else ""
        )
        fix = (
            "Check the spelling of these names and confirm the BED was made for the same genome "
            "build as the reference. Rename or remove the regions that do not exist."
        )
    n_iv = sum(counts.values())
    yield Hit(
        {
            "summary": cap(plural(len(missing), "chromosome name")),
            "contigs": quote_list(missing, 6),
            "hint": hint,
            "fix": fix,
        },
        technical=f"{plural(n_iv, 'interval')} affected. Counts per name: "
        + ", ".join(f"{k}={v}" for k, v in list(counts.items())[:10]),
    )


@check(
    id="BED004",
    severity=Severity.ERROR,
    title="Intervals stay inside their chromosome",
    message=(
        "{count} {extend} beyond the end of {its} chromosome in the reference sequence (for "
        "example, line {line}, {contig} is {length:,} bp long, but the interval ends at {end:,}). "
        "This usually means that the BED was created for a different genome build or contains a "
        "typographical error."
    ),
    detail=(
        "For contigs present in the reference sequence, end must be less than or equal to the "
        "contig length recorded in .fai/.dict."
    ),
    fix=(
        "Please confirm that the BED was created for the same genome build as the reference "
        "sequence (for example, GRCh38, not GRCh37). If it was created for the same genome build, "
        "correct or remove the listed rows."
    ),
    scope="bed",
    requires=("reference",),
)
def bed004(ctx: BedContext) -> Iterator[Hit]:
    assert ctx.reference is not None
    lengths = ctx.reference.lengths
    over = [iv for iv in ctx.bed.intervals if iv.contig in lengths and iv.end > lengths[iv.contig]]
    if over:
        first = over[0]
        yield Hit(
            {
                "count": cap(plural(len(over), "interval")),
                "extend": verb(len(over), "extends", "extend"),
                "its": verb(len(over), "its", "their"),
                "line": first.line,
                "contig": first.contig,
                "length": lengths[first.contig],
                "end": first.end,
            },
            technical="Lines: " + ", ".join(str(iv.line) for iv in over[:10]),
        )


def sort_problem(
    intervals: list[Interval], ref_order: dict[str, int] | None
) -> tuple[str, int] | None:
    """Return (reason, number of out-of-place intervals) if unsorted, else None.

    Sorted means: each chromosome forms one block; starts never decrease inside a block; and the
    blocks are in reference order or in plain alphabetical order.
    """
    blocks: list[str] = []
    out_of_place = 0
    fragmented: list[str] = []
    prev: Interval | None = None
    for iv in intervals:
        if prev is None or iv.contig != prev.contig:
            if iv.contig in blocks:
                if iv.contig not in fragmented:
                    fragmented.append(iv.contig)
                out_of_place += 1
            else:
                blocks.append(iv.contig)
        elif iv.start < prev.start:
            out_of_place += 1
        prev = iv
    if fragmented:
        return (
            "chromosome " + quote_list(fragmented, 3) + " appears in more than one place",
            out_of_place,
        )
    if out_of_place:
        return ("some intervals start before the interval above them", out_of_place)
    alphabetical = blocks == sorted(blocks)
    in_ref_order = False
    if ref_order is not None:
        known = [ref_order[b] for b in blocks if b in ref_order]
        in_ref_order = bool(known) and known == sorted(known)
    if alphabetical or in_ref_order:
        return None
    return ("the chromosomes are in neither reference order nor alphabetical order", len(blocks))


@check(
    id="BED005",
    severity=Severity.WARN,
    title="Intervals are sorted",
    message=(
        "The BED file is not sorted: {reason}. Some commonly used tools (bedtools, tabix, and many "
        "variant callers) require sorted regions. If regions are not sorted, these tools will stop "
        "running or quietly return incorrect results."
    ),
    detail=(
        "Sorted means that each chromosome forms a single continuous block and start positions "
        "within each block do not decrease. These blocks follow reference sequence order (if a "
        "reference sequence is specified) or simple alphabetical order (the order produced by "
        "'sort -k1,1 -k2,2n')."
    ),
    fix=(
        "Run preflight fix-bed --sort <file> --out <sorted file>. To sort in reference sequence "
        "order, add --reference."
    ),
    scope="bed",
)
def bed005(ctx: BedContext) -> Iterator[Hit]:
    order = ctx.reference.order if ctx.reference else None
    result = sort_problem(ctx.bed.intervals, order)
    if result:
        reason, n = result
        yield Hit({"reason": reason}, technical=f"{plural(n, 'interval')} out of place.")


def overlap_stats(intervals: list[Interval]) -> tuple[int, int, int, int, int]:
    """(overlapping, touching, raw_bp, merged_bp, merged_count) over valid intervals."""
    overlapping = touching = raw = merged_total = merged_count = 0
    for group in by_contig(intervals).values():
        spans = sorted((iv.start, iv.end) for iv in group)
        reach: int | None = None
        for start, end in spans:
            raw += end - start
            if reach is not None:
                if start < reach:
                    overlapping += 1
                elif start == reach:
                    touching += 1
            reach = end if reach is None else max(reach, end)
        merged = merge_intervals(spans)
        merged_total += sum(e - s for s, e in merged)
        merged_count += len(merged)
    return overlapping, touching, raw, merged_total, merged_count


@check(
    id="BED006",
    severity=Severity.WARN,
    title="No overlapping or touching intervals",
    message=(
        "{what}. Summing the recorded intervals gives a total target size of {raw}, while coverage "
        "after merging overlaps is only {merged} ({before} regions become {after}). When overlaps "
        "are present, coverage can be counted more than once, and some tools may report the same "
        "region twice."
    ),
    detail=(
        "Intervals are sorted per chromosome. An interval overlaps if it starts before the "
        "furthest end seen so far. If its start position exactly matches that end position, the "
        "intervals are adjacent at their endpoints (book-ended). As in `bedtools merge`, merged "
        "territory is calculated after merging overlapping and book-ended intervals."
    ),
    fix=(
        "Run preflight fix-bed --merge <file> --out <merged file>, or remove duplicates manually."
    ),
    scope="bed",
)
def bed006(ctx: BedContext) -> Iterator[Hit]:
    valid = valid_intervals(ctx.bed)
    overlapping, touching, raw, merged, after = overlap_stats(valid)
    if overlapping or touching:
        parts = []
        if overlapping:
            parts.append(
                f"{plural(overlapping, 'interval')} {verb(overlapping, 'overlaps', 'overlap')} "
                "an earlier interval"
            )
        if touching:
            parts.append(
                f"{plural(touching, 'interval')} {verb(touching, 'touches', 'touch')} the "
                "previous one end to end"
            )
        yield Hit(
            {
                "what": cap(" and ".join(parts)),
                "raw": bp(raw),
                "merged": bp(merged),
                "before": len(valid),
                "after": after,
            },
            technical=(
                f"overlapping={overlapping}, touching={touching}, raw_bp={raw}, merged_bp={merged}"
            ),
        )


def one_based_evidence(intervals: list[Interval]) -> dict[str, int]:
    """Counts used by the BED007 heuristic. See docs/checks.md for the reasoning."""
    gap0 = gap1 = pairs = 0
    zero_start = sum(1 for iv in intervals if iv.start == 0)
    for group in by_contig(intervals).values():
        spans = sorted((iv.start, iv.end) for iv in group)
        reach = spans[0][1]
        for start, end in spans[1:]:
            gap = start - reach
            if gap >= 0:
                pairs += 1
                gap0 += gap == 0
                gap1 += gap == 1
            reach = max(reach, end)
    return {
        "pairs": pairs,
        "gap0": gap0,
        "gap1": gap1,
        "zero_start": zero_start,
    }


def one_based_reasons(ev: dict[str, int]) -> list[str]:
    """Human-readable reasons; empty if the evidence is not strong enough to warn."""
    if ev["zero_start"]:
        return []  # a start of 0 is impossible in a 1-based file
    reasons: list[str] = []
    if (
        ev["gap1"] >= ONE_BASED_MIN_EVIDENCE
        and ev["gap1"] >= 3 * ev["gap0"]
        and ev["gap1"] >= 0.10 * ev["pairs"]
    ):
        reasons.append(
            f"{ev['gap1']} neighbouring regions are separated by a gap of exactly 1 base while "
            f"only {ev['gap0']} touch directly, which is what back-to-back regions look like when "
            "both ends are counted inclusively"
        )
    return reasons


@check(
    id="BED007",
    severity=Severity.WARN,
    title="Coordinates look 0-based (heuristic)",
    message=(
        "This BED file may use coordinates starting at 1. This is a heuristic inference based on "
        "patterns in the file and is not certain ({reasons}). Since BED coordinates start at 0, "
        "all regions would be shifted by 1 base if this file actually uses coordinates starting at "
        "1. This may result in 1 base being missing or added at each boundary."
    ),
    detail=(
        "This heuristic is deliberately conservative and detects only 1 type of evidence. Among "
        "adjacent, non-overlapping region pairs on a chromosome, at least 5 pairs must have a gap "
        "of exactly 1 base. Their number must also be at least 3 times the number of directly "
        "adjoining pairs. These pairs must account for at least 10% of all adjacent region pairs. "
        "If any region starts at 0, 1-based coordinates are ruled out and this check is silenced. "
        "Since this pattern is absent from lists of sparse target regions, most 1-based files "
        "cannot be detected."
    ),
    fix=(
        "Confirm how the file was generated. If coordinates came from a spreadsheet, a 1-based "
        "closed-interval export, or a VCF/GFF list, subtract 1 from the values in the start "
        "column. Leave the values in the end column unchanged. If you are certain that the file is "
        "a 0-based BED file, you can ignore this warning."
    ),
    scope="bed",
    notes=(
        "**Why a heuristic.** BED files do not specify their coordinate convention, and files with "
        "shifted coordinates are still valid BED files. Since only indirect evidence is available, "
        "this check looks for patterns which are relatively rare in files that actually use "
        "0-based coordinates:\n\n*Exactly-one-base gaps between neighbours.* Adjacent 0-based "
        "half-open intervals which cover a genomic segment without gaps share a boundary (the next "
        "interval starts where the previous interval ends). When the same region is represented by "
        "1-based closed intervals, each interval starts exactly 1 position after the previous "
        "interval ends. Gaps of exactly 1 base rarely occur by chance (gaps between targets are "
        "typically tens to thousands of bases). Therefore, a file can be considered suspicious if "
        "it contains many such gaps and few intervals which meet directly at their "
        "boundaries.\n\n*What is deliberately not used.* Coordinates recorded in the name column, "
        "such as `chr1:101-200` for a region starting at 100, cannot be used as evidence for "
        "either case.\n\nEven when a file correctly uses 0-based coordinates, its names often use "
        "1-based coordinates. In hastily created files, column values are used unchanged as names. "
        "Therefore, names cannot be used to distinguish between these cases.\n\nIn files using "
        "1-based coordinates, `start` cannot be 0. Therefore, the check will report nothing if "
        "such intervals are present. Thresholds are fixed in the code (`ONE_BASED_MIN_EVIDENCE = "
        "5` and the ratios above). This check produces false negatives by design.\n\nSparse "
        "interval lists, such as capture panels where exons are sufficiently far apart, have no "
        "identifiable pattern. Detecting these cases requires annotation information based on the "
        "positions where exons begin in known gene models. However, ngs-preflight does not "
        "include this information. Since the aim is to avoid false positives, the check reports "
        "nothing when it cannot be confident."
    ),
)
def bed007(ctx: BedContext) -> Iterator[Hit]:
    ev = one_based_evidence(valid_intervals(ctx.bed))
    reasons = one_based_reasons(ev)
    if reasons:
        yield Hit(
            {"reasons": "; ".join(reasons)},
            technical=", ".join(f"{k}={v}" for k, v in ev.items()),
        )


@check(
    id="BED008",
    severity=Severity.WARN,
    title="Clean file formatting",
    message="{problem} {consequence}",
    detail=(
        "Looks for UTF-8 byte order marks, CRLF (Windows) line endings, spaces used as column "
        "delimiters, and trailing spaces or tabs. Since the parser accepts all 4 cases, the "
        "remaining checks are still run on the cleaned content."
    ),
    fix="{fix}",
    scope="bed",
)
def bed008(ctx: BedContext) -> Iterator[Hit]:
    bed = ctx.bed
    cleanup = "Run: preflight fix-bed <file> --out <clean file> to write a cleaned copy."
    if bed.has_bom:
        yield Hit(
            {
                "problem": "The file starts with a hidden byte-order mark (BOM).",
                "consequence": (
                    "The first chromosome name is then read with invisible extra characters, so "
                    "it will not match the reference."
                ),
                "fix": "Save the file as plain UTF-8 without BOM. " + cleanup,
            }
        )
    if bed.crlf_lines:
        yield Hit(
            {
                "problem": (
                    f"{cap(plural(len(bed.crlf_lines), 'line'))} "
                    f"{verb(len(bed.crlf_lines), 'ends', 'end')} with Windows line endings (CRLF)."
                ),
                "consequence": (
                    "Linux tools treat the invisible carriage return as part of the last column, "
                    "which breaks sorting, merging and name matching."
                ),
                "fix": "Convert to Unix line endings (LF). " + cleanup,
            },
            technical="First lines: " + ", ".join(str(n) for n in bed.crlf_lines[:10]),
        )
    if bed.space_delimited_lines:
        yield Hit(
            {
                "problem": (
                    f"{cap(plural(len(bed.space_delimited_lines), 'line'))} "
                    f"{verb(len(bed.space_delimited_lines), 'separates', 'separate')} the columns "
                    "with spaces instead of tabs."
                ),
                "consequence": "Many tools only accept tabs and will read each line as one column.",
                "fix": "Use a single tab between columns. " + cleanup,
            },
            technical="First lines: " + ", ".join(str(n) for n in bed.space_delimited_lines[:10]),
        )
    if bed.trailing_ws_lines:
        yield Hit(
            {
                "problem": (
                    f"{cap(plural(len(bed.trailing_ws_lines), 'line'))} "
                    f"{verb(len(bed.trailing_ws_lines), 'has', 'have')} extra spaces or tabs at "
                    "the end."
                ),
                "consequence": "The invisible characters can make the last column fail to match.",
                "fix": "Remove the trailing whitespace. " + cleanup,
            },
            technical="First lines: " + ", ".join(str(n) for n in bed.trailing_ws_lines[:10]),
        )


@check(
    id="BED009",
    severity=Severity.INFO,
    title="Territory summary",
    message="{summary}",
    detail=(
        "Counts intervals, total base pairs, base pairs after merging, and size distribution. "
        "Counts intervals on alt/decoy/unplaced contigs (contigs whose names do not match chr1-22, "
        "X, Y, or M, regardless of whether they include 'chr'). Also records whether chrY and chrM "
        "are present and the number of ignored header lines."
    ),
    fix=(
        "No action is required. Confirm that the totals match the expected values for your design "
        "(for example, the panel or exome you ordered)."
    ),
    scope="bed",
)
def bed009(ctx: BedContext) -> Iterator[Hit]:
    bed = ctx.bed
    valid = valid_intervals(bed)
    if not valid:
        return
    sizes = [iv.end - iv.start for iv in valid]
    _o, _t, raw, merged, _n = overlap_stats(valid)
    contigs = by_contig(valid)
    alt = [iv for iv in valid if is_alt_like(iv.contig)]
    alt_contigs = sorted({iv.contig for iv in alt})
    names = {strip_chr(c) for c in contigs}
    parts = [
        f"{cap(plural(len(valid), 'interval'))} on {plural(len(contigs), 'chromosome')}, covering "
        f"{bp(merged)}" + (f" ({mb(merged)})" if merged >= 100_000 else "") + " after merging "
        "overlaps.",
        f"Sizes: smallest {bp(min(sizes))}, median {bp(int(statistics.median(sizes)))}, "
        f"largest {bp(max(sizes))}.",
        f"chrY {'present' if 'Y' in names else 'absent'}; "
        f"chrM {'present' if 'MT' in names else 'absent'}.",
    ]
    if alt:
        parts.append(
            f"{cap(plural(len(alt), 'interval'))} on alt/decoy/unplaced contigs "
            f"({quote_list(alt_contigs, 3)})."
        )
    if bed.header_lines:
        parts.append(f"{cap(plural(len(bed.header_lines), 'header line'))} ignored.")
    yield Hit(
        {"summary": " ".join(parts)},
        technical=(
            f"intervals={len(valid)}, raw_bp={raw}, merged_bp={merged}, "
            f"mean_size={statistics.fmean(sizes):.1f}, style={naming_style(contigs)}"
        ),
    )


@check(
    id="BED010",
    severity=Severity.WARN,
    title="Interval sizes are plausible for a capture panel",
    message=(
        "{what}. Extremely short regions often result from input errors where the start and end "
        "positions are nearly identical. Extremely long regions typically result from accidentally "
        "pasting an entire gene or chromosome. These types of regions behave differently from "
        "standard capture targets."
    ),
    detail=(
        f"Flags intervals shorter than {SMALL_INTERVAL} bp and those longer than "
        f"{LARGE_INTERVAL:,} bp (1 Mb). For designs targeting the whole genome or large regions, "
        "you can ignore this warning."
    ),
    fix=(
        "Check the listed lines. If they are intended (for example, a large linkage region), you "
        "can ignore this warning. Otherwise, correct them."
    ),
    scope="bed",
)
def bed010(ctx: BedContext) -> Iterator[Hit]:
    valid = valid_intervals(ctx.bed)
    small = [iv for iv in valid if iv.end - iv.start < SMALL_INTERVAL]
    large = [iv for iv in valid if iv.end - iv.start > LARGE_INTERVAL]
    if not (small or large):
        return
    parts = []
    if small:
        parts.append(
            f"{plural(len(small), 'interval')} {verb(len(small), 'is', 'are')} shorter than "
            f"{SMALL_INTERVAL} bp"
        )
    if large:
        parts.append(
            f"{plural(len(large), 'interval')} {verb(len(large), 'is', 'are')} longer than 1 Mb"
        )
    tech = []
    if small:
        tech.append("Short, lines: " + ", ".join(str(iv.line) for iv in small[:10]))
    if large:
        tech.append("Long, lines: " + ", ".join(str(iv.line) for iv in large[:10]))
    yield Hit({"what": cap(" and ".join(parts))}, technical=". ".join(tech))


@check(
    id="BED011",
    severity=Severity.WARN,
    title="Interval names are unique",
    message=(
        '{count} {are} used for more than one interval (for example, "{name}" is used {times} '
        "times). Since results are typically reported by name, duplicate names may cause these "
        "results to be merged or overwritten."
    ),
    detail=(
        "This check is only performed when column 4 (name) is present. Empty names and the "
        "placeholder '.' are ignored. Different exons of the same gene often use the same name, "
        "and this is acceptable in some cases."
    ),
    fix=(
        "Ensure that names are unique (for example, by adding exon numbers). Alternatively, if "
        "duplicate names are intentional, ignore this warning."
    ),
    scope="bed",
)
def bed011(ctx: BedContext) -> Iterator[Hit]:
    counts: dict[str, int] = {}
    for iv in ctx.bed.intervals:
        if iv.name and iv.name != ".":
            counts[iv.name] = counts.get(iv.name, 0) + 1
    dup = {k: v for k, v in counts.items() if v > 1}
    if dup:
        name, times = max(dup.items(), key=lambda kv: (kv[1], kv[0]))
        yield Hit(
            {
                "count": cap(plural(len(dup), "name")),
                "are": "is" if len(dup) == 1 else "are",
                "name": name,
                "times": times,
            },
            technical="Repeated: " + ", ".join(f"{k} x{v}" for k, v in list(dup.items())[:10]),
        )
