"""BED checks (BED001-BED011)."""

from __future__ import annotations

import itertools
import re
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
        "{problem} Tools that read this file will stop, or silently skip those lines, so part of "
        "your target regions could be lost."
    ),
    detail=(
        "Each non-header line must have at least 3 columns separated by tabs, where columns 2 and "
        "3 are integers. Lines starting with 'track', 'browser' or '#' are header lines: they are "
        "allowed and counted (see BED009). Blank lines are ignored. Gzip-compressed BED files are "
        "decompressed first."
    ),
    fix=(
        "Open the file and correct or remove the listed lines. Each line needs a chromosome name, "
        "a start and an end, separated by tabs, with start and end as whole numbers."
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
        "{count} {have} impossible coordinates (for example line {line}: start {start:,}, end "
        "{end:,}). A region must start at 0 or later and end after it starts; empty or backwards "
        "regions are rejected by most tools or silently ignored."
    ),
    detail="Every interval must satisfy 0 <= start < end. BED is 0-based, half-open.",
    fix=(
        "Check the start and end columns on the listed lines. If start and end were swapped, swap "
        "them back; empty regions (start equal to end) can be deleted."
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
        "{summary} in the BED file cannot be found in the reference: {contigs}. {hint} "
        "Tools will fail or skip these regions, so the data you expect to be analysed would be "
        "missing."
    ),
    detail=(
        "Every contig name in column 1 is compared, exactly and case-sensitively, with the "
        "sequence names in the reference .fai/.dict. If adding or removing a 'chr' prefix "
        "(including MT <-> chrM) would make every missing name match, the message says so and "
        "points to 'preflight fix-bed'."
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
        "{count} {extend} past the end of {its} chromosome in the reference (for example line "
        "{line}: {contig} is {length:,} bp long but the interval ends at {end:,}). This usually "
        "means the BED was made for a different genome build, or has typing errors."
    ),
    detail=(
        "For contigs present in the reference, end must be <= the contig length from the "
        ".fai/.dict."
    ),
    fix=(
        "Confirm the BED was made for the same genome build as the reference (for example GRCh38, "
        "not GRCh37). If it was, correct or remove the listed lines."
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
        in_ref_order = known == sorted(known)
    if alphabetical or in_ref_order:
        return None
    return ("the chromosomes are in neither reference order nor alphabetical order", len(blocks))


@check(
    id="BED005",
    severity=Severity.WARN,
    title="Intervals are sorted",
    message=(
        "The BED file is not sorted: {reason}. Several common tools (bedtools, tabix, many "
        "variant callers) need sorted regions and will stop, or quietly give wrong answers, "
        "if they are not."
    ),
    detail=(
        "Sorted means every chromosome is one contiguous block, starts do not decrease inside a "
        "block, and the blocks follow either the reference order (when a reference is given) or "
        "plain alphabetical order (as produced by 'sort -k1,1 -k2,2n')."
    ),
    fix=(
        "Run: preflight fix-bed --sort <file> --out <sorted file>. Add --reference to sort in "
        "reference order."
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
        "{what}. Counted as written, the targets add up to {raw}, but they cover only {merged} "
        "once overlaps are merged ({before} regions become {after}). Overlaps can double-count "
        "coverage and make some tools report the same region twice."
    ),
    detail=(
        "Intervals are sorted per chromosome. An interval that starts before the furthest end seen "
        "so far overlaps; one that starts exactly at that end is book-ended (touching). Merged "
        "territory is computed after joining both kinds, like 'bedtools merge'."
    ),
    fix=(
        "Run: preflight fix-bed --merge <file> --out <merged file>, or remove the duplicates "
        "by hand."
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


_NUMBER = re.compile(r"\d+")


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
    name_plus1 = name_exact = named = 0
    for iv in intervals:
        if not iv.name:
            continue
        nums = [int(x) for x in _NUMBER.findall(iv.name)]
        if len(nums) < 2:
            continue
        named += 1
        in_name = set(itertools.pairwise(nums))
        if (iv.start + 1, iv.end) in in_name:
            name_plus1 += 1
        if (iv.start, iv.end) in in_name:
            name_exact += 1
    return {
        "pairs": pairs,
        "gap0": gap0,
        "gap1": gap1,
        "zero_start": zero_start,
        "named_with_coords": named,
        "name_start_plus1": name_plus1,
        "name_start_exact": name_exact,
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
    if (
        ev["name_start_plus1"] >= ONE_BASED_MIN_EVIDENCE
        and ev["name_start_plus1"] >= 5 * ev["name_start_exact"]
    ):
        reasons.append(
            f"{ev['name_start_plus1']} region names contain coordinates that equal the BED start "
            "plus one"
        )
    return reasons


@check(
    id="BED007",
    severity=Severity.WARN,
    title="Coordinates look 0-based (heuristic)",
    message=(
        "This BED file may use 1-based coordinates. This is a heuristic guess from patterns in "
        "the file, not a certainty: {reasons}. BED files are 0-based, so if the file really is "
        "1-based, every region would be shifted by one base, which can drop or add a base at "
        "every edge."
    ),
    detail=(
        "Heuristic, and deliberately conservative. It looks for two kinds of evidence and only "
        "warns when one is strong. (1) Gap pattern: among neighbouring non-overlapping regions on "
        "a chromosome, at least 5 are separated by exactly 1 base, at least 3 times as many as "
        "touch directly, and they make up at least 10% of neighbour pairs. (2) Name pattern: at "
        "least 5 region names embed a coordinate pair (such as chr1:101-200) that equals "
        "start+1 and end, and at least 5 times as many as match start and end exactly. "
        "A start of 0 anywhere rules out 1-based and silences the check. Sparse target lists "
        "carry no such patterns, so most 1-based files cannot be detected."
    ),
    fix=(
        "Check how the file was produced. If the coordinates came from a spreadsheet, a "
        "1-based 'closed interval' export or a VCF/GFF-style list, subtract 1 from the start "
        "column and leave the end column alone. If you are sure the file is 0-based BED, you "
        "can ignore this warning."
    ),
    scope="bed",
    notes=(
        "**Why a heuristic.** A BED file does not say which convention it uses, and a shifted "
        "file is still valid BED. The only evidence available is indirect, so this check looks "
        "for patterns that are rare in genuine 0-based files:\n\n"
        "1. *Exactly-one-base gaps between neighbours.* Adjacent 0-based half-open regions that "
        "tile a stretch of genome share a boundary (the next start equals the previous end). The "
        "same regions written as 1-based closed intervals show a gap of exactly 1 between them. "
        "A gap of exactly 1 base is rare by chance (gaps between targets are usually tens to "
        "thousands of bases), so a file with many of them and few direct touches is suspicious.\n"
        "2. *Coordinates written in the name column.* Names such as `chr1:101-200` or "
        "`amp_101_200` record the source coordinates. If they equal `start+1` and `end` rather "
        "than `start` and `end`, the source was 1-based.\n\n"
        "A `start` of 0 is impossible in a 1-based file, so any such interval silences the "
        "check. The thresholds are fixed in code (`ONE_BASED_MIN_EVIDENCE = 5` and the ratios "
        "above). The check has false negatives by design: sparse lists, such as a capture panel "
        "with well-separated exons, carry no pattern, and detecting those would need an "
        "annotation (exon starts from a known gene model), which ngs-preflight does not ship. "
        "It is meant to avoid false alarms, so it stays silent when unsure."
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
        "Looks for a UTF-8 byte-order mark, CRLF (Windows) line endings, spaces used as column "
        "separators, and trailing spaces or tabs at the end of a line. The parser tolerates all "
        "four, so the other checks still run on the cleaned content."
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
        "Counts intervals, total and merged base pairs, the size distribution, intervals on "
        "alt/decoy/unplaced contigs (any name that is not chr1-22, X, Y or M, with or without "
        "'chr'), presence of chrY and chrM, and the number of header lines that were ignored."
    ),
    fix=(
        "No action needed. Check that the totals match what you expect for your design "
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
        "{what}. Very short regions are often typing mistakes (a start and end that are almost "
        "equal), and very long ones are usually whole genes or chromosomes pasted in by "
        "mistake; neither behaves like normal capture targets."
    ),
    detail=(
        f"Flags intervals shorter than {SMALL_INTERVAL} bp and longer than {LARGE_INTERVAL:,} bp "
        "(1 Mb). Whole-genome or large-region designs can ignore this warning."
    ),
    fix=(
        "Check the listed lines. If they are intended (for example a large linkage region), you "
        "can ignore this warning; otherwise correct them."
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
        '{count} {are} used for more than one interval (for example "{name}", {times} times). '
        "Results are often reported per name, so repeated names can be merged together or "
        "overwrite each other."
    ),
    detail=(
        "Only runs when column 4 (name) is present. Empty names and the placeholder '.' are "
        "ignored. Repeated names for different exons of one gene are common and may be fine."
    ),
    fix=(
        "Make the names unique (for example add an exon number), or ignore this warning if "
        "repeated names are intended."
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
