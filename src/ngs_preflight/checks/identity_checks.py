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
        'Samples "{a}" and "{b}" have almost identical genotypes (relatedness {relatedness:.2f}, '
        "where 1.0 means the same person). Two different sample IDs should not hold the same "
        "individual: this is either a duplicate submitted under two names, or a sample swap."
    ),
    detail=(
        "somalier relate compares genotypes at about 17,000 common sites. Any pair of different "
        f"sample IDs with relatedness above {DUPLICATE_RELATEDNESS} is reported. Identical twins "
        "and the same person sequenced twice cannot be told apart by this test."
    ),
    fix=(
        "Check with the submitter which sample each file really belongs to. If one is a repeat of "
        "the other, give them the same sample ID and a different library or lane, or drop one."
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
        'The sample sheet says "{parent}" is the {role} of "{child}", but their genomes are only '
        "{relatedness:.2f} related (a parent and child should be about 0.50). Either the family "
        "tree in the sheet is wrong, or a sample has been swapped or mislabelled."
    ),
    detail=(
        "For every declared parent-child pair with both samples present, relatedness from somalier "
        f"relate must fall between {PARENT_CHILD_RANGE[0]} and {PARENT_CHILD_RANGE[1]} (expected "
        "0.5). Father and son swapped in the sheet is still parent-child, but the other parent "
        "link then fails, which is how swaps are usually caught."
    ),
    fix=(
        "Check the paternal_id / maternal_id columns against the family you were told about. If "
        "the sheet is right, ask the lab to confirm the sample labels."
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
        'Samples "{a}" and "{b}" are not declared as relatives in the sample sheet, but their '
        "genomes are {relatedness:.2f} related (unrelated people are close to 0). They may be "
        "relatives that the sheet does not mention, or the sheet may be incomplete."
    ),
    detail=(
        f"Pairs with relatedness between {UNRELATED_RELATEDNESS} and {DUPLICATE_RELATEDNESS} are "
        "reported when the sheet gives no relationship between them. Samples in the same "
        "family_id, parent-child pairs and siblings (sharing a declared parent) are never "
        "reported. Samples that are not in the sheet are not reported."
    ),
    fix=(
        "If these people are related, add the family_id and parent columns. If they should not "
        "be related, ask the lab whether samples were mixed up."
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
        'The sample sheet says "{sample}" is {declared}, but the data look {inferred} '
        "(X-chromosome heterozygosity and X/Y read depth). Either the sex in the sheet is wrong "
        "or the sample has been mixed up."
    ),
    detail=(
        "somalier infers sex per sample from heterozygous calls on chrX and relative depth on "
        "chrX and chrY. Reported when the sheet says male or female and somalier infers the "
        "opposite. Samples declared unknown, or where somalier cannot decide, are not reported. "
        "Needs enough chrX/chrY sites; with very low coverage the call may be absent. When "
        "somalier makes no call (it uses read depth, which VCF input does not have), the sex is "
        "taken from chrX instead: under 5% heterozygous among non-reference calls is male, over "
        "25% is female, anything else (or fewer than 20 such sites) is unknown."
    ),
    fix=(
        "Check the sex entered for this sample. If the sheet is right, ask the lab to confirm "
        "the sample was not swapped."
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
        'Only {sites:,} of the identity sites could be read in "{sample}" ({low} is the minimum '
        "we consider reliable). With so few, the relatedness and sex results for this sample "
        "may be wrong, so treat the identity checks on it as unconfirmed."
    ),
    detail=(
        f"Informative sites are those somalier genotyped as homozygous reference, heterozygous or "
        f"homozygous alternate. Fewer than {MIN_INFORMATIVE_SITES:,} (about 28% of the 17,766 "
        "sites in the standard hg38 list) triggers this warning. Typical causes: low coverage, "
        "a targeted panel that does not cover the sites, or a VCF without hom-ref records."
    ),
    fix=(
        "Use deeper data or a whole-genome/exome file for the identity check. For targeted "
        "panels, consider whether the identity check is meaningful at all."
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
