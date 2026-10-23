"""Data-driven tests: one hand-made fixture per failure mode, each with an expected-result JSON.

Every check in the BED and sample-sheet groups must have at least one positive fixture (it fires)
and at least one negative fixture (a file where it must stay quiet).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ngs_preflight.registry import checks_for_scope
from tests.conftest import DATA, REF37, REF38
from tests.helpers import check, ids

BED_CASES = sorted((DATA / "bed").glob("*.bed"))
SHEET_CASES = sorted(
    [*(DATA / "samplesheets").glob("*.csv"), *(DATA / "samplesheets").glob("*.tsv")]
)


def _expected(path: Path) -> dict[str, object]:
    name = path.name.rsplit(".", 1)[0]
    return json.loads(path.with_name(name + ".expected.json").read_text())  # type: ignore[no-any-return]


@pytest.mark.parametrize("bed", BED_CASES, ids=lambda p: p.stem)
def test_bed_fixture(bed: Path) -> None:
    exp = _expected(bed)
    ref = REF37 if exp["reference"] == "grch37" else REF38
    report = check(beds=[str(bed)], reference=str(ref))
    assert ids(report) == set(exp["checks"]), [  # type: ignore[call-overload]
        (f.check_id, f.message) for f in report.all_findings()
    ]
    assert report.exit_code in (0, 1, 2)


@pytest.mark.parametrize("sheet", SHEET_CASES, ids=lambda p: p.stem)
def test_samplesheet_fixture(sheet: Path) -> None:
    exp = _expected(sheet)
    reads = str(DATA / "reads") if exp["reads_dir"] else None
    report = check(samplesheet=str(sheet), reads_dir=reads)
    assert ids(report) == set(exp["checks"]), [  # type: ignore[call-overload]
        (f.check_id, f.message) for f in report.all_findings()
    ]


def test_every_bed_and_sheet_check_has_positive_and_negative_fixtures() -> None:
    fired: set[str] = set()
    for path in BED_CASES + SHEET_CASES:
        fired |= set(_expected(path)["checks"])  # type: ignore[call-overload]
    for scope in ("bed", "samplesheet"):
        for spec in checks_for_scope(scope):  # type: ignore[arg-type]
            if spec.severity.value == "INFO":
                continue
            assert spec.id in fired, f"{spec.id} has no positive fixture"
            quiet = [p for p in BED_CASES + SHEET_CASES if spec.id not in _expected(p)["checks"]]  # type: ignore[operator]
            assert quiet, f"{spec.id} has no negative fixture"


def test_bed009_summary_always_present_for_readable_bed() -> None:
    report = check(beds=[str(DATA / "bed" / "ok_basic.bed")], reference=str(REF38))
    infos = [f for f in report.all_findings() if f.check_id == "BED009"]
    assert len(infos) == 1
    assert "4 intervals on 3 chromosomes" in infos[0].message
    assert "chrY absent" in infos[0].message


def test_bed_header_lines_are_reported_as_ignored() -> None:
    report = check(beds=[str(DATA / "bed" / "ok_header_lines.bed")], reference=str(REF38))
    summary = next(f for f in report.all_findings() if f.check_id == "BED009")
    assert "3 header lines ignored" in summary.message


def test_bed003_suggests_add_chr() -> None:
    report = check(beds=[str(DATA / "bed" / "bed003_missing_chr_prefix.bed")], reference=str(REF38))
    f = next(f for f in report.all_findings() if f.check_id == "BED003")
    assert "fix-bed --add-chr" in f.fix
    assert '"chr1"' in f.message


def test_bed003_suggests_strip_chr_for_plain_reference() -> None:
    report = check(beds=[str(DATA / "bed" / "bed003_strip_chr_needed.bed")], reference=str(REF37))
    f = next(f for f in report.all_findings() if f.check_id == "BED003")
    assert "fix-bed --strip-chr" in f.fix


def test_bed003_unknown_contig_gives_generic_advice() -> None:
    report = check(beds=[str(DATA / "bed" / "bed003_unknown_contig.bed")], reference=str(REF38))
    f = next(f for f in report.all_findings() if f.check_id == "BED003")
    assert "fix-bed" not in f.fix
    assert "chrZZ" in f.message


def test_bed003_mt_to_chrm() -> None:
    report = check(beds=[str(DATA / "bed" / "bed003_mt_naming.bed")], reference=str(REF38))
    f = next(f for f in report.all_findings() if f.check_id == "BED003")
    assert '"MT"' in f.message and "add-chr" in f.fix


def test_skipped_checks_are_listed_with_reason_when_no_reference() -> None:
    report = check(beds=[str(DATA / "bed" / "ok_basic.bed")])
    skipped = {s.check_id: s.reason for s in report.skipped}
    assert set(skipped) == {"BED003", "BED004"}
    assert "--reference" in skipped["BED003"]


def test_sheet_checks_skipped_without_reads_dir() -> None:
    report = check(samplesheet=str(DATA / "samplesheets" / "ok_full.csv"))
    assert {s.check_id for s in report.skipped} == {"SS004", "SS007"}


def test_alignment_rows_need_no_fastq_2(tmp_path: Path) -> None:
    from tests.helpers import make_bam

    make_bam(tmp_path / "slice.bam", {"chr1": 1000})
    sheet = tmp_path / "s.csv"
    for text in (
        "sample_id,fastq_1,sex\nHG002,slice.bam,male\n",
        "sample_id,fastq_1,fastq_2,sex\nHG002,slice.bam,,male\n",
    ):
        sheet.write_text(text)
        report = check(samplesheet=str(sheet), reads_dir=str(tmp_path))
        assert not any(f.severity.value == "ERROR" for f in report.all_findings()), text
        assert "SS001" not in ids(report)


def test_fastq_rows_still_need_fastq_2(tmp_path: Path) -> None:
    sheet = tmp_path / "s.csv"
    sheet.write_text("sample_id,fastq_1,sex\nA,A_R1.fastq.gz,male\n")
    assert "SS001" in ids(check(samplesheet=str(sheet)))
    sheet.write_text("sample_id,fastq_1,fastq_2\nA,A_R1.fastq.gz,\nB,b.bam,\n")
    report = check(samplesheet=str(sheet))
    blank = [f for f in report.all_findings() if f.check_id == "SS001"]
    assert len(blank) == 1 and "line 2" in blank[0].message
    sheet.write_text("sample_id,fastq_1,sex\nA,A_R1.fastq.gz,male\nB,b.bam,male\n")
    assert "SS001" in ids(check(samplesheet=str(sheet)))
