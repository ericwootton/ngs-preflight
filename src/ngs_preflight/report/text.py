"""Terminal report built with rich. Colour is a bonus: every state also has a word and a symbol."""

from __future__ import annotations

import io

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from ngs_preflight.models import Finding, Report, Severity
from ngs_preflight.report.common import counts, file_verdict, label, overall_verdict

_STYLE = {
    "PASS": "bold green",
    "WARN": "bold yellow",
    "FAIL": "bold red",
    "INFO": "cyan",
    "N/A": "dim",
}
_SEV_STYLE = {Severity.ERROR: "bold red", Severity.WARN: "bold yellow", Severity.INFO: "cyan"}


def finding_line(f: Finding) -> Text:
    """``[ERROR BED003] targets.bed: <message> Fix: <fix>``."""
    line = Text()
    line.append(f"[{f.severity.value} {f.check_id}]", style=_SEV_STYLE[f.severity])
    line.append(f" {f.file}: {f.message} ")
    line.append("Note: " if f.severity is Severity.INFO else "Fix: ", style="bold")
    line.append(f.fix)
    return line


def render_text(report: Report, color: bool = False, width: int = 100) -> str:
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        force_terminal=color,
        color_system="standard" if color else None,
        width=width,
        legacy_windows=False,
        highlight=False,
    )
    verdict = overall_verdict(report)
    head = Text()
    head.append(f"{label(verdict)}  ", style=_STYLE[verdict])
    head.append(report.headline, style="bold")
    console.print(head)
    s = report.summary
    console.print(
        Text(
            f"ngs-preflight {report.tool.version} | {s.errors} errors, {s.warnings} warnings, "
            f"{s.infos} notes | {s.checks_run} checks run, {s.checks_skipped} skipped"
            + (" | strict mode" if report.strict else ""),
            style="dim",
        )
    )
    console.print()

    table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False)
    table.add_column("File", overflow="fold")
    table.add_column("Type")
    table.add_column("Errors", justify="right")
    table.add_column("Warnings", justify="right")
    table.add_column("Notes", justify="right")
    table.add_column("Result")
    for fr in report.files:
        e, w, i = counts(fr)
        v = file_verdict(fr, report.strict)
        table.add_row(
            fr.path,
            fr.kind,
            Text(str(e), style="red" if e else ""),
            Text(str(w), style="yellow" if w else ""),
            str(i),
            Text(label(v), style=_STYLE[v]),
        )
    console.print(table)

    findings = [f for fr in report.files for f in fr.findings]
    if findings:
        console.print()
    for f in sorted(findings, key=lambda x: (x.severity.rank, x.file, x.check_id)):
        console.print(finding_line(f))
        if f.technical:
            console.print(Text(f"    Technical: {f.technical}", style="dim"))
    if report.skipped:
        console.print()
        console.print(Text("Skipped checks", style="bold"))
        for sk in report.skipped:
            where = f" ({sk.file})" if sk.file else ""
            console.print(Text(f"  - {sk.check_id} {sk.title}{where}: {sk.reason}", style="dim"))
    console.print()
    took = f" in {report.duration_seconds:.2f}s" if report.duration_seconds is not None else ""
    console.print(
        Text(
            f"Generated {report.generated_at}{took}. Explain any check: preflight explain <ID>",
            style="dim",
        )
    )
    return buffer.getvalue()
