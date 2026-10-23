"""Sample identity checks (ID001-ID005), driven by somalier output."""

from __future__ import annotations

from collections.abc import Iterator

from ngs_preflight.context import Declared, IdentityContext
from ngs_preflight.models import Severity
from ngs_preflight.registry import Hit, check
from ngs_preflight.util import cap, plural

DUPLICATE_RELATEDNESS = 0.9
PARENT_CHILD_RANGE = (0.35, 0.65)
UNRELATED_RELATEDNESS = 0.2
MIN_INFORMATIVE_SITES = 5000


def _relations(declared: dict[str, Declared]) -> tuple[set[frozenset[str]], set[frozenset[str]]]:
    """(parent-child pairs, pairs the sheet says are related in some other way)."""
    parent_child: set[frozenset[str]] = set()
    kin: set[frozenset[str]] = set()
    for d in declared.values():
        for parent in (d.father, d.mother):
            if parent and parent in declared:
                parent_child.add(frozenset({d.sample_id, parent}))
    by_parent: dict[str, list[str]] = {}
    for d in declared.values():
        for parent in (d.father, d.mother):
            if parent:
                by_parent.setdefault(parent, []).append(d.sample_id)
    for children in by_parent.values():
        for i, a in enumerate(children):
            for b in children[i + 1 :]:
                kin.add(frozenset({a, b}))  # siblings (share a declared parent)
    ids = list(declared)
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            fa, fb = declared[a].family, declared[b].family
            if fa and fa == fb:
                kin.add(frozenset({a, b}))  # same family: relationship unknown, not "unrelated"
    return parent_child, kin | parent_child


@check(
    id="ID001",
    severity=Severity.ERROR,
    title="No two samples are the same person",
    message=(
        'Samples "{a}" and "{b}" have nearly identical genotypes (relatedness {relatedness:.2f}, '
        "where 1.0 indicates the same individual). 2 different sample IDs must not refer to the "
        "same individual. Either the same sample was submitted under 2 names, or a sample mix-up "
        "occurred."
    ),
    detail=(
        "somalier relate compares genotypes at about 17,000 common sites. All pairs with "
        f"different sample IDs and relatedness above {DUPLICATE_RELATEDNESS} are reported. This "
        "check cannot distinguish identical twins from sequencing the same individual twice."
    ),
    fix=(
        "Confirm with the submitter which sample each file actually belongs to. If one is a "
        "duplicate of the other, assign them the same sample ID and different library or "
        "sequencing lane values, or exclude one."
    ),
    scope="identity",
)
def id001(ctx: IdentityContext) -> Iterator[Hit]:
    for p in ctx.result.pairs:
        if p.sample_a != p.sample_b and p.relatedness > DUPLICATE_RELATEDNESS:
            yield Hit(
                {"a": p.sample_a, "b": p.sample_b, "relatedness": p.relatedness},
                technical=f"IBS0={p.ibs0}, IBS2={p.ibs2}, sites compared={p.n}.",
            )


@check(
    id="ID002",
    severity=Severity.ERROR,
    title="Declared parent and child are related as expected",
    message=(
        'The sample sheet lists "{parent}" as the {role} of "{child}", but their genetic '
        "relatedness is only {relatedness:.2f} (about 0.50 would be expected for a parent and "
        "child). Either the pedigree in the sample sheet is incorrect, or the samples have been "
        "mixed up or mislabelled."
    ),
    detail=(
        "For all declared parent-child pairs where both samples are present, relatedness "
        f"calculated by somalier relate must be within {PARENT_CHILD_RANGE[0]}-"
        f"{PARENT_CHILD_RANGE[1]} (expected value of 0.5). Even if the father and son are swapped "
        "in the sample sheet, they remain a parent-child pair. However, this swap can usually be "
        "detected because the relationship with the other parent would no longer meet the "
        "criteria."
    ),
    fix=(
        "Check the paternal_id / maternal_id columns against the supplied pedigree information. If "
        "the sample sheet is correct, ask the laboratory to check the sample labels."
    ),
    scope="identity",
)
def id002(ctx: IdentityContext) -> Iterator[Hit]:
    lo, hi = PARENT_CHILD_RANGE
    for d in ctx.declared.values():
        for role, parent in (("father", d.father), ("mother", d.mother)):
            if (
                not parent
                or parent not in ctx.result.samples
                or d.sample_id not in ctx.result.samples
            ):
                continue
            pair = ctx.result.pair(d.sample_id, parent)
            if pair is None:
                continue
            if not lo <= pair.relatedness <= hi:
                yield Hit(
                    {
                        "parent": parent,
                        "role": role,
                        "child": d.sample_id,
                        "relatedness": pair.relatedness,
                    },
                    technical=f"IBS0={pair.ibs0}, IBS2={pair.ibs2}, sites compared={pair.n}.",
                )


@check(
    id="ID003",
    severity=Severity.WARN,
    title="Unrelated samples are unrelated",
    message=(
        'Samples "{a}" and "{b}" are not listed as related in the sample sheet, but their genomic '
        "relatedness is {relatedness:.2f} (close to 0 for unrelated individuals). They may be "
        "relatives which the sample sheet does not mention, or the sample sheet may be incomplete."
    ),
    detail=(
        f"Sample pairs with relatedness between {UNRELATED_RELATEDNESS} and "
        f"{DUPLICATE_RELATEDNESS} are reported if their relationship is not recorded in the sample "
        "sheet. Pairs within the same family_id, parent-child pairs, and sibling pairs (samples "
        "which share a declared parent) are never reported. Samples absent from the sample sheet "
        "are not reported."
    ),
    fix=(
        "If these individuals are related, add the family_id and parent columns. If these "
        "individuals are expected to be unrelated, check with the laboratory whether a sample "
        "mix-up has occurred."
    ),
    scope="identity",
)
def id003(ctx: IdentityContext) -> Iterator[Hit]:
    _pc, kin = _relations(ctx.declared)
    for p in ctx.result.pairs:
        if p.sample_a not in ctx.declared or p.sample_b not in ctx.declared:
            continue
        if not UNRELATED_RELATEDNESS < p.relatedness <= DUPLICATE_RELATEDNESS:
            continue
        if frozenset({p.sample_a, p.sample_b}) in kin:
            continue
        yield Hit(
            {"a": p.sample_a, "b": p.sample_b, "relatedness": p.relatedness},
            technical=f"IBS0={p.ibs0}, IBS2={p.ibs2}, sites compared={p.n}.",
        )


@check(
    id="ID004",
    severity=Severity.ERROR,
    title="Declared sex matches the data",
    message=(
        'The sample sheet lists "{sample}" as {declared}, but the data suggest {inferred} (X '
        "chromosome heterozygosity and X/Y read depth). Either the sex recorded in the sample "
        "sheet is incorrect, or the sample has been mixed up."
    ),
    detail=(
        "somalier infers sex per sample using heterozygous calls on chrX and relative depth on "
        "chrX and chrY. A discrepancy is reported when the sample sheet says male or female and "
        "somalier infers the opposite sex. Samples declared unknown or whose sex somalier cannot "
        "determine are not reported. This determination requires enough sites on chrX/chrY, and "
        "very low coverage may prevent a result. somalier uses read depth, which VCF input does "
        "not have. When somalier makes no call, sex is inferred from chrX instead. If heterozygous "
        "variants account for less than 5% of non-reference variant calls, the sample is "
        "classified as male. If this proportion is greater than 25%, the sample is classified as "
        "female. Other cases, including samples with fewer than 20 such sites, are unknown."
    ),
    fix=(
        "Check the sex recorded for this sample. If the sample sheet is correct, ask the "
        "laboratory to confirm that no sample mix-up occurred."
    ),
    scope="identity",
)
def id004(ctx: IdentityContext) -> Iterator[Hit]:
    for sid, s in ctx.result.samples.items():
        d = ctx.declared.get(sid)
        if d is None or d.sex is None or s.inferred_sex == "unknown":
            continue
        if d.sex != s.inferred_sex:
            yield Hit(
                {"sample": sid, "declared": d.sex, "inferred": s.inferred_sex},
                technical=(
                    f"X depth={s.x_depth_mean}, Y depth={s.y_depth_mean}, X het sites={s.x_het}."
                ),
            )


@check(
    id="ID005",
    severity=Severity.WARN,
    title="Enough informative sites for an identity call",
    message=(
        'Only {sites:,} sample identity sites were readable for "{sample}" (we consider {low} '
        "sites the minimum for reliable results). With so few sites, the relatedness and sex "
        "results for this sample may be incorrect, so treat its sample identity checks as "
        "unconfirmed."
    ),
    detail=(
        "Informative sites are sites which somalier classifies as homozygous for the reference "
        "allele, heterozygous, or homozygous for the alternate allele. This warning is displayed "
        f"when their number is below {MIN_INFORMATIVE_SITES:,} (about 28% of the 17,766 sites in "
        "the standard hg38 list). Typical causes include low coverage, targeted panels which do "
        "not cover these sites, or a lack of hom-ref records in the VCF."
    ),
    fix=(
        "Use data with higher sequencing depth or whole-genome or whole-exome files to verify "
        "sample identity. For targeted panels, consider whether verifying sample identity is "
        "meaningful."
    ),
    scope="identity",
)
def id005(ctx: IdentityContext) -> Iterator[Hit]:
    for sid, s in ctx.result.samples.items():
        if s.informative_sites < MIN_INFORMATIVE_SITES:
            yield Hit(
                {"sites": s.informative_sites, "sample": sid, "low": f"{MIN_INFORMATIVE_SITES:,}"},
                technical=(
                    f"hom_ref={s.n_hom_ref}, het={s.n_het}, hom_alt={s.n_hom_alt}, "
                    f"unknown={s.n_unknown}, mean depth={s.depth_mean}. "
                    + cap(plural(s.informative_sites, "informative site"))
                    + "."
                ),
            )
