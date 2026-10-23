"""Reference compatibility checks (REF001-REF003): reference vs BED vs read-file headers."""

from __future__ import annotations

from collections.abc import Iterator

from ngs_preflight.context import CrossContext, ReadsInfo
from ngs_preflight.contigs import (
    add_chr,
    detect_build,
    is_primary,
    naming_style,
    strip_chr,
)
from ngs_preflight.models import Severity
from ngs_preflight.registry import Hit, check
from ngs_preflight.util import cap, plural, quote_list

_STYLE_WORDS = {"chr": 'with a "chr" prefix (chr1)', "plain": "without a prefix (1)"}


def _normalised(lengths: dict[str, int]) -> dict[str, int]:
    return {strip_chr(k): v for k, v in lengths.items() if is_primary(k)}


def _inspectable(reads: list[ReadsInfo]) -> list[ReadsInfo]:
    return [r for r in reads if r.header is not None]


@check(
    id="REF001",
    severity=Severity.ERROR,
    title="Reference, BED and reads agree on naming and genome build",
    message=("{problem} {consequence}"),
    detail=(
        "Naming style is read from the primary chromosomes (1-22, X, Y, M with or without "
        "'chr'). A BAM header is compared with the reference; when there is no reference, the BED "
        "is compared with the BAM header instead (the BED-versus-reference case is reported in "
        "detail by BED003). Genome build is compared by contig length: the same chromosome with "
        "a different length means a different build (for example GRCh37 chr1 is 249,250,621 bp, "
        "GRCh38 chr1 is 248,956,422 bp). With --expected-build, the reference itself is also "
        "recognised by its lengths and compared with the expected build. Only BAM headers are "
        "read; see REF003."
    ),
    fix="{fix}",
    scope="cross",
)
def ref001(ctx: CrossContext) -> Iterator[Hit]:
    ref = ctx.reference
    reads = _inspectable(ctx.reads)
    ref_style = naming_style(ref.lengths) if ref else "unknown"
    ref_norm = _normalised(ref.lengths) if ref else {}
    for r in reads:
        assert r.header is not None
        style = naming_style(r.header.references)
        if ref and ref_style in _STYLE_WORDS and style in _STYLE_WORDS and style != ref_style:
            yield Hit(
                {
                    "problem": (
                        f"The reads file spells chromosomes {_STYLE_WORDS[style]}, but the "
                        f"reference spells them {_STYLE_WORDS[ref_style]}."
                    ),
                    "consequence": (
                        "Aligners and callers match chromosomes by name, so the reads and the "
                        "reference would not line up and the run would fail or analyse nothing."
                    ),
                    "fix": (
                        "Use reads and a reference built with the same naming (re-align or "
                        "re-header the reads, or choose the matching reference). Do not edit "
                        "chromosome names by hand in a BAM."
                    ),
                },
                file=r.path,
                technical=(
                    f"reads style={style}, reference style={ref_style}; sample {r.sample_id}."
                ),
            )
            continue
        if ref:
            rlen = _normalised(r.header.references)
            differing = [k for k in rlen if k in ref_norm and rlen[k] != ref_norm[k]]
            if differing:
                b_reads = detect_build(r.header.references) or "an unknown build"
                b_ref = detect_build(ref.lengths) or "an unknown build"
                k = differing[0]
                yield Hit(
                    {
                        "problem": (
                            f"The reads file and the reference look like different genome builds "
                            f"({plural(len(differing), 'chromosome')} have different lengths; "
                            f"chromosome {k} is {rlen[k]:,} bp in the reads but {ref_norm[k]:,} "
                            "bp in the reference)."
                        ),
                        "consequence": (
                            "Coordinates would not mean the same thing in the two files, so "
                            "results would be wrong or the run would stop with a dictionary error."
                        ),
                        "fix": (
                            "Find out which genome build each file uses and supply matching "
                            "files. The reads must be aligned to the same reference build."
                        ),
                    },
                    file=r.path,
                    technical=f"reads build: {b_reads}; reference build: {b_ref}.",
                )
    if not ref:
        for bed_path, bed in ctx.bed_files:
            bed_style = naming_style({iv.contig for iv in bed.intervals})
            for r in reads:
                assert r.header is not None
                style = naming_style(r.header.references)
                if bed_style in _STYLE_WORDS and style in _STYLE_WORDS and bed_style != style:
                    yield Hit(
                        {
                            "problem": (
                                f"The BED file spells chromosomes {_STYLE_WORDS[bed_style]}, but "
                                f"the reads file spells them {_STYLE_WORDS[style]}."
                            ),
                            "consequence": (
                                "The target regions would not match any reads, so coverage and "
                                "calls over the targets would be empty."
                            ),
                            "fix": (
                                "Run: preflight fix-bed --"
                                + ("add-chr" if style == "chr" else "strip-chr")
                                + " on the BED to match the reads."
                            ),
                        },
                        file=bed_path,
                        technical=f"BED style={bed_style}, reads style={style} ({r.path}).",
                    )
                    break
    expected = ctx.expected_build
    if ref and expected:
        found = detect_build(ref.lengths)
        if found and found != expected:
            yield Hit(
                {
                    "problem": (
                        f"The reference looks like {found}, but {expected} was expected "
                        f"(its chromosome lengths match {found})."
                    ),
                    "consequence": (
                        "Everything else in the submission (target BED, reads, truth sets) must "
                        "use the same build, and tools built for one build give wrong answers "
                        "on the other."
                    ),
                    "fix": (
                        f"Supply a {expected} reference, or tell us which build you intend to use."
                    ),
                },
                file=ctx.reference_path,
                technical=f"detected={found}, expected={expected}.",
            )


@check(
    id="REF002",
    severity=Severity.WARN,
    title="Reads and reference list the same chromosomes",
    message=(
        "{problem} Some tools stop on this mismatch (for example with a sequence dictionary "
        "error), and any reads on the missing chromosomes would be ignored."
    ),
    detail=(
        "Compares the chromosome names in a BAM header with the reference. Reports names in the "
        "BAM that the reference lacks, and primary chromosomes (1-22, X, Y, M) the reference has "
        "but the BAM header lacks. Not reported when the naming style differs (REF001 explains "
        "that case)."
    ),
    fix=(
        "Align the reads to the same reference you are submitting, or supply the reference the "
        "reads were aligned to. For a deliberately partial BAM, make sure its header lists only "
        "the chromosomes it contains."
    ),
    scope="cross",
    requires=("reference",),
)
def ref002(ctx: CrossContext) -> Iterator[Hit]:
    ref = ctx.reference
    assert ref is not None
    ref_style = naming_style(ref.lengths)
    for r in _inspectable(ctx.reads):
        assert r.header is not None
        names = set(r.header.references)
        if naming_style(names) != ref_style and naming_style(names) in _STYLE_WORDS:
            continue
        extra = [n for n in r.header.references if n not in ref.lengths]
        absent = [
            n for n in ref.lengths if is_primary(n) and n not in names and add_chr(n) not in names
        ]
        parts = []
        if extra:
            parts.append(
                f"the reads file lists {plural(len(extra), 'chromosome')} the reference does "
                f"not have ({quote_list(extra, 4)})"
            )
        if absent:
            parts.append(
                f"the reference has {plural(len(absent), 'main chromosome')} the reads file does "
                f"not list ({quote_list(absent, 4)})"
            )
        if parts:
            yield Hit(
                {"problem": cap("; ".join(parts)) + "."},
                file=r.path,
                technical=f"sample {r.sample_id}; header has {len(names)} contigs, reference "
                f"{len(ref.lengths)}.",
            )


@check(
    id="REF003",
    severity=Severity.INFO,
    title="Read-file header could not be inspected",
    message="{reason} The reference compatibility checks (REF001, REF002) did not cover this file.",
    detail=(
        "BAM headers are read directly. CRAM headers are not inspected by this version, and a BAM "
        "whose header cannot be parsed is reported here (integrity problems are reported by "
        "SS007)."
    ),
    fix="No action needed. If compatibility matters, confirm this file's reference by other means.",
    scope="cross",
)
def ref003(ctx: CrossContext) -> Iterator[Hit]:
    for r in ctx.reads:
        if r.header is None and r.note:
            yield Hit({"reason": r.note}, file=r.path, technical=f"sample {r.sample_id}")
