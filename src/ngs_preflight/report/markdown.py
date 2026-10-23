"""Markdown report (for tickets, pull requests and email)."""

from __future__ import annotations

from ngs_preflight.models import Report
from ngs_preflight.report.common import KIND_LABELS, counts, file_verdict, label, overall_verdict


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(report: Report) -> str:
    out: list[str] = []
    out.append(f"# Preflight report: {label(overall_verdict(report))}")
    out.append("")
    out.append(f"**{report.headline}.**")
    out.append("")
    s = report.summary
    out.append(
        f"{s.errors} errors, {s.warnings} warnings, {s.infos} notes. "
        f"{s.checks_run} checks run, {s.checks_skipped} skipped."
        + (" Strict mode: warnings count as errors." if report.strict else "")
    )
    out.append("")
    out.append("| File | Type | Errors | Warnings | Notes | Result |")
    out.append("|---|---|---:|---:|---:|---|")
    for fr in report.files:
        e, w, i = counts(fr)
        out.append(
            f"| `{_cell(fr.path)}` | {KIND_LABELS[fr.kind]} | {e} | {w} | {i} | "
            f"{label(file_verdict(fr, report.strict))} |"
        )
    for fr in report.files:
        if not fr.findings:
            continue
        out.append("")
        out.append(f"## `{fr.path}`")
        for f in fr.findings:
            out.append("")
            out.append(f"### {f.severity.value} {f.check_id}: {f.title}")
            out.append("")
            out.append(f"**What this means.** {f.message}")
            out.append("")
            out.append(
                f"**{'What to do' if f.severity.value == 'INFO' else 'How to fix'}.** {f.fix}"
            )
            out.append("")
            out.append("<details><summary>Technical detail</summary>")
            out.append("")
            out.append(f.detail)
            if f.technical:
                out.append("")
                out.append(f"Evidence: {f.technical}")
            out.append("")
            out.append("</details>")
    if report.skipped:
        out.append("")
        out.append("## Skipped checks")
        out.append("")
        for sk in report.skipped:
            where = f" (`{sk.file}`)" if sk.file else ""
            out.append(f"- **{sk.check_id}** {sk.title}{where}: {sk.reason}")
    out.append("")
    took = f" in {report.duration_seconds:.2f}s" if report.duration_seconds is not None else ""
    out.append(f"*ngs-preflight {report.tool.version}, generated {report.generated_at}{took}.*")
    out.append("")
    return "\n".join(out)
