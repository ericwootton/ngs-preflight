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
from ngs_preflight.util import cap, plural, quote_list, verb

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
        "Naming format is determined from the primary chromosomes (1-22, X, Y, M, with or without "
        "'chr'). A BAM header is compared to the reference sequence. If no reference sequence is "
        "available, the BED is compared to the BAM header instead (the BED comparison to the "
        "reference sequence is reported in detail in BED003).\n\nGenome build is determined by "
        "comparing contig lengths. Different lengths indicate different genome builds even for the "
        "same chromosome (for example, chr1 has a length of 249,250,621 bp in GRCh37 and chr1 has "
        "a length of 248,956,422 bp in GRCh38). When --expected-build is specified, the "
        "reference's own genome build is also identified from its sequence lengths and compared to "
        "the expected build. Only the BAM header is read. See REF003."
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
                            f"({plural(len(differing), 'chromosome')} "
                            f"{verb(len(differing), 'has a', 'have')} different "
                            f"{verb(len(differing), 'length', 'lengths')}; "
                            f"chromosome {k} is {rlen[k]:,} bp in the reads but {ref_norm[k]:,} "
                            "bp in the reference)."
                        ),
                        "consequence": (
                            "Coordinates would not mean the same thing in the two files, so "
                            "results would be wrong, and some tools stop with a sequence "
                            "dictionary error."
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
        "{problem} GATK and DeepVariant currently accept this situation. However, stricter tools "
        "may not accept it, and reads on chromosomes absent from the reference sequence will be "
        "ignored."
    ),
    detail=(
        "Compares the chromosome names in the BAM header to those in the reference sequence. "
        "Reports names present in the BAM but absent from the reference sequence. Also reports "
        "primary chromosomes (1-22, X, Y, M) present in the reference sequence but absent from the "
        "BAM header. These differences are not reported when the naming style differs (this is "
        "described in REF001)."
    ),
    fix=(
        "Align reads to the same reference sequence you submitted, or provide the reference "
        "sequence used to align them. For an intentionally partial BAM, confirm that its header "
        "lists only the chromosomes included in that BAM."
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
    message=(
        "{reason} This file was not included in the reference sequence compatibility checks "
        "(REF001, REF002)."
    ),
    detail=(
        "BAM headers are read directly. This version does not check CRAM headers. BAM files whose "
        "headers cannot be parsed are reported here (integrity problems are reported by SS007)."
    ),
    fix=(
        "No action is required. If compatibility matters, confirm this file's reference using "
        "another method."
    ),
    scope="cross",
)
def ref003(ctx: CrossContext) -> Iterator[Hit]:
    for r in ctx.reads:
        if r.header is None and r.note:
            yield Hit({"reason": r.note}, file=r.path, technical=f"sample {r.sample_id}")
