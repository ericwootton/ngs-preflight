"""CLI behaviour (exit codes, formats, explain, fix-bed, docs) and the shape of each report."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ngs_preflight import __version__
from ngs_preflight.cli import main
from ngs_preflight.docs_gen import generated_files, stale_docs
from ngs_preflight.models import Report
from ngs_preflight.registry import all_checks
from ngs_preflight.report.html import render_html
from ngs_preflight.report.json_report import render_json, report_json_schema
from ngs_preflight.report.markdown import render_markdown
from ngs_preflight.report.text import render_text
from tests.conftest import DATA, REF38, ROOT
from tests.helpers import check


def code(argv: list[str]) -> int:
    """main() result, treating argparse's own SystemExit as the exit code."""
    try:
        return main(argv)
    except SystemExit as exc:
        return int(exc.code or 0)


GOOD = ROOT / "examples" / "good"
MESSY = ROOT / "examples" / "messy"
EXAMPLE_REF = str(REF38)


def _args(folder: Path) -> list[str]:
    return [
        "check",
        "--samplesheet", str(folder / "samples.csv"),
        "--bed", str(folder / "targets.bed"),
        "--reference", EXAMPLE_REF,
        "--reads-dir", str(folder / "reads"),
    ]  # fmt: skip


def test_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(_args(GOOD)) == 0
    assert main(_args(MESSY)) == 1
    warn_bed = tmp_path / "w.bed"
    warn_bed.write_text("chr1\t1000\t1300\ta\nchr1\t1200\t1500\tb\n")  # overlap: warning only
    assert main(["check", "--bed", str(warn_bed), "--reference", EXAMPLE_REF]) == 2
    assert main(["check", "--bed", str(warn_bed), "--reference", EXAMPLE_REF, "--strict"]) == 1
    capsys.readouterr()


def test_usage_errors_exit_3(capsys: pytest.CaptureFixture[str]) -> None:
    assert code(["check"]) == 3
    assert code(["check", "--bed", "/no/such/file.bed"]) == 3
    assert (
        code(["check", "--bed", str(DATA / "bed" / "bed001_ok.bed"), "--reference", "/nope.fai"])
        == 3
    )
    assert code(["bogus-command"]) == 3
    assert code(["check", "--format", "pdf", "--bed", "x"]) == 3
    assert code(["explain", "NOPE999"]) == 3
    err = capsys.readouterr().err
    assert "error" in err


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


@pytest.mark.parametrize("fmt", ["text", "json", "markdown", "html"])
def test_formats_to_file(tmp_path: Path, fmt: str, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / f"r.{fmt}"
    code = main([*_args(MESSY), "--format", fmt, "--out", str(out)])
    assert code == 1
    assert out.stat().st_size > 500
    assert "Report written to" in capsys.readouterr().out


def test_stdout_json_is_valid(capsys: pytest.CaptureFixture[str]) -> None:
    main([*_args(MESSY), "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert data["schema_version"] == "1.0"
    assert data["exit_code"] == 1


def test_explain_every_check(capsys: pytest.CaptureFixture[str]) -> None:
    for spec in all_checks():
        assert main(["explain", spec.id.lower()]) == 0
        out = capsys.readouterr().out
        assert out.startswith(f"{spec.id}: {spec.title}")
        assert "How to fix it:" in out
        assert f"ngs-preflight/checks/#{spec.id.lower()}" in out


def test_explain_suggests_close_ids(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["explain", "BED03"]) == 3
    assert "Did you mean" in capsys.readouterr().err


def test_fix_bed_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = tmp_path / "t.bed"
    src.write_text("1\t500\t600\n1\t100\t200\n")
    assert main(["fix-bed", str(src), "--add-chr", "--sort"]) == 0
    out = capsys.readouterr().out
    assert "was not changed" in out
    assert (tmp_path / "t.fixed.bed").read_text().startswith("chr1\t100\t200")
    assert main(["fix-bed", str(src), "--add-chr"]) == 3  # output exists
    assert code(["fix-bed", str(src), "--add-chr", "--strip-chr"]) == 3
    capsys.readouterr()


def test_docs_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["docs", "--out-dir", str(tmp_path)]) == 0
    assert main(["docs", "--out-dir", str(tmp_path), "--check"]) == 0
    (tmp_path / "checks.md").write_text("stale")
    assert main(["docs", "--out-dir", str(tmp_path), "--check"]) == 1
    capsys.readouterr()


# --- committed docs and examples must match what the code generates -------------------------


def test_committed_docs_are_not_stale() -> None:
    stale = stale_docs(ROOT / "docs")
    assert not stale, "run 'preflight docs' to regenerate: " + ", ".join(map(str, stale))


def test_every_check_is_documented() -> None:
    text = (ROOT / "docs" / "checks.md").read_text(encoding="utf-8")
    for spec in all_checks():
        assert f'<a id="{spec.id.lower()}">' in text
    assert set(generated_files()) == {"checks.md", "report.schema.json"}


def test_examples_are_not_stale() -> None:
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_examples.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


# --- report content -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def messy() -> Report:
    return check(
        samplesheet=str(MESSY / "samples.csv"),
        beds=[str(MESSY / "targets.bed")],
        reference=EXAMPLE_REF,
        reads_dir=str(MESSY / "reads"),
    )


@pytest.fixture(scope="module")
def good() -> Report:
    return check(
        samplesheet=str(GOOD / "samples.csv"),
        beds=[str(GOOD / "targets.bed")],
        reference=EXAMPLE_REF,
        reads_dir=str(GOOD / "reads"),
    )


def test_html_is_self_contained_and_accessible(messy: Report) -> None:
    html = render_html(messy)
    assert "<script" not in html
    assert not re.search(r'(src|href)="https?://', html)
    assert "<link" not in html and "@import" not in html and "url(" not in html
    for needle in ("What this means", "How to fix", "Technical detail", "<details>", 'lang="en"'):
        assert needle in html
    # status is conveyed with words and symbols, not only colour
    assert "FAIL" in html and "Error" in html and "✖" in html
    assert 'class="skip"' in html
    assert "prefers-color-scheme: dark" in html


def test_html_escapes_content(tmp_path: Path) -> None:
    bed = tmp_path / "a&b.bed"
    bed.write_text("chr1\t5\t3\n")
    html = render_html(check(beds=[str(bed)], reference=EXAMPLE_REF))
    assert "a&b.bed" not in html
    assert "a&amp;b.bed" in html


def test_good_report_passes(good: Report) -> None:
    assert good.exit_code == 0 and good.status == "pass"
    for text in (render_text(good), render_markdown(good), render_html(good)):
        assert "Ready to run" in text


def test_json_schema_and_roundtrip(messy: Report) -> None:
    data = json.loads(render_json(messy))
    assert data["schema_version"] == "1.0"
    assert Report.model_validate(data).summary.errors == messy.summary.errors
    schema = report_json_schema()
    assert schema["title"] == "ngs-preflight report"
    committed = json.loads((ROOT / "docs" / "report.schema.json").read_text(encoding="utf-8"))
    assert committed == schema
    for key in (
        "tool",
        "generated_at",
        "status",
        "exit_code",
        "headline",
        "summary",
        "files",
        "skipped",
    ):
        assert key in data
    finding = next(f for fr in data["files"] for f in fr["findings"])
    assert {
        "check_id",
        "severity",
        "title",
        "file",
        "message",
        "fix",
        "detail",
        "technical",
    } <= set(finding)


def test_markdown_and_text_group_by_file(messy: Report) -> None:
    md = render_markdown(messy)
    assert md.startswith("# Preflight report: ")
    assert "**What this means.**" in md and "**How to fix.**" in md
    text = render_text(messy)
    assert "[ERROR SS002]" in text and "Fix:" in text


def test_reproducible_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")
    a = check(beds=[str(MESSY / "targets.bed")], reference=EXAMPLE_REF)
    b = check(beds=[str(MESSY / "targets.bed")], reference=EXAMPLE_REF)
    assert render_json(a) == render_json(b)
    assert a.duration_seconds is None and a.generated_at == "2026-01-01T00:00:00Z"


def test_color_text_output(messy: Report) -> None:
    assert "\x1b[" in render_text(messy, color=True)
    assert "\x1b[" not in render_text(messy, color=False)


def test_python_m_entry_point() -> None:
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "ngs_preflight", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0 and __version__ in proc.stdout


def test_summary_counts_agree_in_number() -> None:
    good = (Path(__file__).resolve().parents[1] / "examples" / "reports" / "good.md").read_text(
        "utf-8"
    )
    assert "0 errors, 0 warnings, 1 note. 20 checks run" in good
