"""Run the optional identity checks: extract, relate, then evaluate ID001-ID005."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from ngs_preflight.context import Declared, IdentityContext
from ngs_preflight.errors import PreflightError
from ngs_preflight.identity.somalier import (
    EXTRACTABLE_SUFFIXES,
    SOMALIER_SUFFIX,
    SUPPORTED_VERSION,
    SomalierError,
    SomalierRunner,
)
from ngs_preflight.registry import checks_for_scope
from ngs_preflight.samplesheet import SampleSheet, load_schema

if TYPE_CHECKING:
    from ngs_preflight.runner import Options, _Collector

PSEUDO_FILE = "sample identity"


def declared_from_sheet(sheet: SampleSheet | None) -> dict[str, Declared]:
    """One :class:`Declared` per sample_id (first row wins)."""
    declared: dict[str, Declared] = {}
    if sheet is None:
        return declared
    schema = load_schema()
    none_markers = {m.lower() for m in schema.no_parent_markers}
    for row in sheet.rows:
        if not row.sample_id or row.sample_id in declared:
            continue
        sex = schema.sex.classify(row.sex) if row.sex else None
        declared[row.sample_id] = Declared(
            sample_id=row.sample_id,
            sex=sex if sex in {"male", "female"} else None,
            father=None if row.paternal_id.lower() in none_markers else row.paternal_id,
            mother=None if row.maternal_id.lower() in none_markers else row.maternal_id,
            family=row.family_id,
        )
    return declared


def _inputs_from_sheet(sheet: SampleSheet | None, reads_dir: str | None) -> list[Path]:
    found: list[Path] = []
    if sheet is None:
        return found
    for row in sheet.rows:
        for value in (row.fastq_1, row.fastq_2):
            if value.lower().endswith((".bam", ".cram")):
                p = Path(value)
                if not p.is_absolute() and reads_dir:
                    p = Path(reads_dir) / p
                if p.is_file() and p not in found:
                    found.append(p)
    return found


def run_identity_checks(opts: Options, sheet: SampleSheet | None, col: _Collector) -> None:
    specs = checks_for_scope("identity")

    def skip_all(reason: str) -> None:
        for spec in specs:
            col.skip(spec, PSEUDO_FILE, reason)

    runner = SomalierRunner(opts.somalier_cmd)
    ok, info = runner.available()
    if not ok:
        skip_all(
            f"somalier is not available ({info}). Install somalier {SUPPORTED_VERSION} "
            "(https://github.com/brentp/somalier) or point --somalier-cmd at it."
        )
        return
    inputs = [Path(p) for p in opts.identity_inputs] or _inputs_from_sheet(sheet, opts.reads_dir)
    if not inputs:
        skip_all(
            "no files were given for the identity check. Pass BAM, CRAM, VCF or .somalier files "
            "with --alignments-or-vcfs."
        )
        return
    for p in inputs:
        if not p.is_file():
            raise PreflightError(f"identity input not found: {p}")
        if not (p.name.endswith(SOMALIER_SUFFIX) or p.name.lower().endswith(EXTRACTABLE_SUFFIXES)):
            raise PreflightError(
                f"cannot use {p.name} for identity checks: expected BAM, CRAM, VCF or .somalier"
            )

    sites = Path(opts.sites) if opts.sites else None
    fasta = Path(opts.fasta) if opts.fasta else None
    declared = declared_from_sheet(sheet)
    with tempfile.TemporaryDirectory(prefix="preflight-") as tmp:
        tmp_dir = Path(tmp)
        somalier_files: list[Path] = []
        for p in inputs:
            if p.name.endswith(SOMALIER_SUFFIX):
                somalier_files.append(p)
                continue
            if sites is None or not sites.is_file():
                skip_all(
                    "the sites file is needed to read BAM/CRAM/VCF files (use --sites "
                    "sites.hg38.vcf.gz), or pass pre-extracted .somalier files instead."
                )
                return
            try:
                somalier_files += runner.extract(p, sites, fasta, tmp_dir / "extracted")
            except SomalierError as exc:
                skip_all(f"somalier could not read {p.name}: {exc}")
                return
        try:
            result = runner.relate(somalier_files, sites, tmp_dir / "relate")
        except SomalierError as exc:
            skip_all(f"somalier relate failed: {exc}")
            return
    ctx = IdentityContext(result=result, declared=declared)
    col.run_scope(specs, ctx, PSEUDO_FILE, "identity", lambda s: None)
