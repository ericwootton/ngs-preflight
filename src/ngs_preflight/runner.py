"""Orchestration: load inputs, run the registered checks, build the :class:`Report`."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ngs_preflight import __version__
from ngs_preflight.bam import BamError, read_bam_header
from ngs_preflight.bed import BedFile, read_bed
from ngs_preflight.context import BedContext, CrossContext, ReadsInfo, SheetContext
from ngs_preflight.errors import PreflightError
from ngs_preflight.models import (
    FileKind,
    FileResult,
    Finding,
    Report,
    Severity,
    SkippedCheck,
    Status,
    Summary,
    ToolInfo,
)
from ngs_preflight.reference import Reference, load_reference
from ngs_preflight.registry import CheckSpec, Hit, checks_for_scope
from ngs_preflight.samplesheet import SampleSheet, load_schema, read_samplesheet
from ngs_preflight.util import plural

IDENTITY_PSEUDO_FILE = "sample identity"
COMPAT_PSEUDO_FILE = "reference compatibility"


@dataclass
class Options:
    samplesheet: str | None = None
    beds: list[str] = field(default_factory=list)
    reference: str | None = None
    reads_dir: str | None = None
    identity: bool = False
    sites: str | None = None
    identity_inputs: list[str] = field(default_factory=list)
    fasta: str | None = None
    somalier_cmd: str | None = None
    expected_build: str | None = None
    strict: bool = False


def _now() -> datetime:
    """UTC now, or a fixed time when SOURCE_DATE_EPOCH is set (reproducible output)."""
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch and epoch.isdigit():
        return datetime.fromtimestamp(int(epoch), tz=UTC)
    return datetime.now(UTC)


def reproducible() -> bool:
    return bool(os.environ.get("SOURCE_DATE_EPOCH", "").isdigit())


class _Collector:
    """Accumulates per-file results and skipped checks while checks run."""

    def __init__(self) -> None:
        self.files: dict[str, FileResult] = {}
        self.skipped: list[SkippedCheck] = []

    def file(self, path: str, kind: FileKind) -> FileResult:
        if path not in self.files:
            self.files[path] = FileResult(path=path, kind=kind)
        return self.files[path]

    def skip(self, spec: CheckSpec, file: str | None, reason: str) -> None:
        self.skipped.append(
            SkippedCheck(check_id=spec.id, title=spec.title, file=file, reason=reason)
        )

    def add_hits(
        self, spec: CheckSpec, hits: Iterable[Hit], default_file: str, kind: FileKind
    ) -> int:
        n = 0
        for hit in hits:
            target = hit.file or default_file
            target_kind: FileKind = kind if target == default_file else "reads"
            fr = self.file(target, target_kind)
            fr.findings.append(
                Finding(
                    check_id=spec.id,
                    severity=hit.severity or spec.severity,
                    title=spec.title,
                    file=target,
                    message=spec.render_message(hit.params),
                    fix=spec.render_fix(hit.params),
                    detail=spec.detail,
                    technical=hit.technical,
                )
            )
            n += 1
        return n

    def run_scope(
        self,
        specs: list[CheckSpec],
        ctx: Any,
        file: str,
        kind: FileKind,
        unavailable: Callable[[CheckSpec], str | None],
    ) -> None:
        for spec in specs:
            reason = unavailable(spec)
            if reason:
                self.skip(spec, file, reason)
                continue
            fr = self.file(file, kind)
            fr.checks_run.append(spec.id)
            n = self.add_hits(spec, spec.func(ctx), file, kind)
            if n == 0:
                fr.checks_passed.append(spec.id)


def _read_infos(sheet: SampleSheet, reads_dir: Path | None) -> list[ReadsInfo]:
    """BAM/CRAM files named in the sample sheet that exist on disk, with their headers."""
    infos: list[ReadsInfo] = []
    seen: set[Path] = set()
    for row in sheet.rows:
        for value in (row.fastq_1, row.fastq_2):
            lowered = value.lower()
            if not lowered.endswith((".bam", ".cram")) or "://" in value:
                continue
            p = Path(value)
            if not p.is_absolute() and reads_dir is not None:
                p = reads_dir / p
            if p in seen or not p.is_file():
                continue
            seen.add(p)
            if lowered.endswith(".cram"):
                infos.append(
                    ReadsInfo(
                        value,
                        row.sample_id,
                        "cram",
                        note=f'The header of "{value}" was not inspected because CRAM headers '
                        "are not read by this version.",
                    )
                )
                continue
            try:
                header = read_bam_header(p)
                infos.append(ReadsInfo(value, row.sample_id, "bam", header=header))
            except (BamError, OSError) as exc:
                infos.append(
                    ReadsInfo(
                        value,
                        row.sample_id,
                        "bam",
                        note=f'The header of "{value}" could not be read ({exc}).',
                    )
                )
    return infos


def finalize(findings: list[Finding], strict: bool) -> tuple[Status, int, str]:
    errors = sum(f.severity is Severity.ERROR for f in findings)
    warnings = sum(f.severity is Severity.WARN for f in findings)
    if errors:
        extra = f" (and {plural(warnings, 'warning')} to review)" if warnings else ""
        return "errors", 1, f"Fix {plural(errors, 'error')} before submitting{extra}"
    if warnings and strict:
        return (
            "errors",
            1,
            f"Fix {plural(warnings, 'warning')} before submitting (strict mode treats warnings "
            "as errors)",
        )
    if warnings:
        return "warnings", 2, f"Ready to run, with {plural(warnings, 'warning')} worth reviewing"
    return "pass", 0, "Ready to run"


def run_preflight(opts: Options) -> Report:
    started = time.monotonic()
    if not (opts.samplesheet or opts.beds or opts.reference):
        raise PreflightError(
            "nothing to check: give at least one of --samplesheet, --bed or --reference"
        )
    if opts.expected_build and opts.expected_build not in {"GRCh38", "GRCh37"}:
        raise PreflightError("--expected-build must be GRCh38 or GRCh37")

    reference: Reference | None = load_reference(opts.reference) if opts.reference else None
    reads_dir = Path(opts.reads_dir) if opts.reads_dir else None
    if reads_dir is not None and not reads_dir.is_dir():
        raise PreflightError(f"--reads-dir is not a folder: {reads_dir}")

    col = _Collector()
    if reference is not None:
        col.file(opts.reference or "", "reference")

    # BED files
    beds: list[tuple[str, BedFile]] = []
    for path in opts.beds:
        bed = read_bed(path)
        beds.append((path, bed))
        ctx_b = BedContext(path=path, bed=bed, reference=reference)
        col.run_scope(
            checks_for_scope("bed"),
            ctx_b,
            path,
            "bed",
            lambda s: (
                "no reference was given (use --reference)"
                if "reference" in s.requires and reference is None
                else None
            ),
        )

    # Sample sheet
    sheet: SampleSheet | None = None
    reads: list[ReadsInfo] = []
    if opts.samplesheet:
        sheet = read_samplesheet(opts.samplesheet)
        ctx_s = SheetContext(
            path=opts.samplesheet, sheet=sheet, schema=load_schema(), reads_dir=reads_dir
        )
        col.run_scope(
            checks_for_scope("samplesheet"),
            ctx_s,
            opts.samplesheet,
            "samplesheet",
            lambda s: (
                "no read-file folder was given (use --reads-dir)"
                if "reads_dir" in s.requires and reads_dir is None
                else None
            ),
        )
        reads = _read_infos(sheet, reads_dir)

    # Cross-file reference compatibility
    cross = CrossContext(
        reference=reference,
        reference_path=opts.reference,
        expected_build=opts.expected_build,
        bed_files=beds,
        reads=reads,
    )
    cross_file = opts.reference or COMPAT_PSEUDO_FILE
    cross_reason = None
    if not reads and not (reference and opts.expected_build):
        cross_reason = (
            "there are no BAM files to compare (FASTQ files carry no chromosome header, and "
            "BAMs are only found when --reads-dir and the sample sheet point at them)"
        )

    def cross_unavailable(spec: CheckSpec) -> str | None:
        if cross_reason:
            return cross_reason
        if "reference" in spec.requires and reference is None:
            return "no reference was given (use --reference)"
        return None

    if reference is not None or reads:
        col.run_scope(
            checks_for_scope("cross"),
            cross,
            cross_file,
            "reference",
            cross_unavailable,
        )

    # Sample identity (optional)
    if opts.identity:
        from ngs_preflight.identity.run import run_identity_checks

        run_identity_checks(opts, sheet, col)

    files = list(col.files.values())
    findings = [f for fr in files for f in fr.findings]
    for fr in files:
        fr.findings.sort(key=lambda f: (f.severity.rank, f.check_id))
    status, code, headline = finalize(findings, opts.strict)
    summary = Summary(
        errors=sum(f.severity is Severity.ERROR for f in findings),
        warnings=sum(f.severity is Severity.WARN for f in findings),
        infos=sum(f.severity is Severity.INFO for f in findings),
        files=len(files),
        checks_run=sum(len(fr.checks_run) for fr in files),
        checks_skipped=len(col.skipped),
    )
    return Report(
        tool=ToolInfo(version=__version__),
        generated_at=_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        duration_seconds=None if reproducible() else round(time.monotonic() - started, 3),
        strict=opts.strict,
        status=status,
        exit_code=code,
        headline=headline,
        summary=summary,
        files=files,
        skipped=col.skipped,
    )
