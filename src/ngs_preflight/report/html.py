"""Single-file HTML report: no external assets, no scripts, readable without colour."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ngs_preflight.models import Report, Severity
from ngs_preflight.report.common import (
    KIND_LABELS,
    SYMBOLS,
    counts,
    file_verdict,
    overall_verdict,
)

_TEMPLATES = Path(__file__).parent / "templates"
SEVERITY_WORDS = {Severity.ERROR: "Error", Severity.WARN: "Warning", Severity.INFO: "Note"}
SEVERITY_SYMBOLS = {
    Severity.ERROR: SYMBOLS["FAIL"],
    Severity.WARN: SYMBOLS["WARN"],
    Severity.INFO: SYMBOLS["INFO"],
}


def render_html(report: Report) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("report.html.j2")
    verdict = overall_verdict(report)
    files: list[dict[str, Any]] = []
    for fr in report.files:
        e, w, i = counts(fr)
        files.append(
            {
                "result": fr,
                "kind_label": KIND_LABELS[fr.kind],
                "verdict": file_verdict(fr, report.strict),
                "errors": e,
                "warnings": w,
                "notes": i,
                "anchor": "file-" + str(len(files) + 1),
            }
        )
    return template.render(
        report=report,
        verdict=verdict,
        symbols=SYMBOLS,
        files=files,
        sev_word=SEVERITY_WORDS,
        sev_symbol=SEVERITY_SYMBOLS,
    )
