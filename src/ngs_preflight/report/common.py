"""Helpers shared by the report writers."""

from __future__ import annotations

from ngs_preflight.models import FileResult, Report, Severity

SYMBOLS = {"PASS": "✔", "WARN": "⚠", "FAIL": "✖", "INFO": "ℹ", "N/A": "–"}
KIND_LABELS = {
    "bed": "Target regions (BED)",
    "samplesheet": "Sample sheet",
    "reference": "Reference",
    "reads": "Read file",
    "identity": "Sample identity",
}


def file_verdict(fr: FileResult, strict: bool) -> str:
    """PASS, WARN or FAIL for one file (WARN counts as FAIL in strict mode)."""
    if not fr.checks_run and not fr.findings:
        return "N/A"  # used only as the comparison for other files
    if any(f.severity is Severity.ERROR for f in fr.findings):
        return "FAIL"
    if any(f.severity is Severity.WARN for f in fr.findings):
        return "FAIL" if strict else "WARN"
    return "PASS"


def overall_verdict(report: Report) -> str:
    return {"pass": "PASS", "warnings": "WARN", "errors": "FAIL"}[report.status]


def counts(fr: FileResult) -> tuple[int, int, int]:
    e = sum(f.severity is Severity.ERROR for f in fr.findings)
    w = sum(f.severity is Severity.WARN for f in fr.findings)
    i = sum(f.severity is Severity.INFO for f in fr.findings)
    return e, w, i


def label(verdict: str) -> str:
    return f"{SYMBOLS[verdict]} {verdict}"
