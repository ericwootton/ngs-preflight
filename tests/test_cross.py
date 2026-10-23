"""Cross-file checks (REF001-REF003): reference vs BED vs the headers of BAM files."""

from __future__ import annotations

from pathlib import Path

from ngs_preflight.contigs import GRCH37_LENGTHS, GRCH38_LENGTHS
from tests.conftest import REF37, REF38
from tests.helpers import check, ids, make_bam

CHR_REFS = {"chr1": 248956422, "chr2": 242193529, "chrX": 156040895}


def _sheet(tmp: Path, reads: str) -> str:
    p = tmp / "samples.csv"
    p.write_text(f"sample_id,fastq_1,fastq_2\nS1,{reads},\n")
    return str(p)


def _run(tmp: Path, refs: dict[str, int], reference: Path = REF38, **kw: object):  # type: ignore[no-untyped-def]
    make_bam(tmp / "s1.bam", refs)
    return check(
        samplesheet=_sheet(tmp, "s1.bam"), reads_dir=str(tmp), reference=str(reference), **kw
    )


def test_matching_bam_is_clean(tmp_path: Path) -> None:
    refs = {f"chr{k}": v for k, v in GRCH38_LENGTHS.items()} | {"chrM": 16569}
    report = _run(tmp_path, refs)
    assert not ids(report) & {"REF001", "REF002"}


def test_ref001_naming_style_mismatch(tmp_path: Path) -> None:
    report = _run(tmp_path, dict(GRCH38_LENGTHS))
    assert "REF001" in ids(report)
    f = next(x for x in report.all_findings() if x.check_id == "REF001")
    assert "chr" in f.message and f.file == "s1.bam"
    assert "REF002" not in ids(report)  # the style mismatch is explained once


def test_ref001_build_mismatch(tmp_path: Path) -> None:
    report = _run(tmp_path, {f"chr{k}": v for k, v in GRCH37_LENGTHS.items()})
    assert "REF001" in ids(report)
    f = next(x for x in report.all_findings() if x.check_id == "REF001")
    assert "genome builds" in f.message
    assert "GRCh37" in f.technical


def test_ref001_bam_vs_bed_without_reference(tmp_path: Path) -> None:
    make_bam(tmp_path / "s1.bam", CHR_REFS)
    bed = tmp_path / "t.bed"
    bed.write_text("1\t100\t200\n2\t100\t200\n")
    report = check(samplesheet=_sheet(tmp_path, "s1.bam"), reads_dir=str(tmp_path), beds=[str(bed)])
    f = next(x for x in report.all_findings() if x.check_id == "REF001")
    assert f.file == str(bed)
    assert "fix-bed --add-chr" in f.fix


def test_ref001_expected_build(tmp_path: Path) -> None:
    report = check(reference=str(REF37), expected_build="GRCh38")
    f = next(x for x in report.all_findings() if x.check_id == "REF001")
    assert "GRCh37" in f.message and "GRCh38" in f.message
    assert not ids(check(reference=str(REF38), expected_build="GRCh38"))


def test_ref002_missing_contigs_both_ways(tmp_path: Path) -> None:
    report = _run(tmp_path, {"chr1": 248956422, "chrZZ": 5})
    f = next(x for x in report.all_findings() if x.check_id == "REF002")
    assert "chrZZ" in f.message
    assert "main chromosome" in f.message


def test_ref003_cram_and_unreadable_bam(tmp_path: Path) -> None:
    (tmp_path / "a.cram").write_bytes(b"CRAM")
    (tmp_path / "b.bam").write_bytes(b"junk")
    sheet = tmp_path / "s.csv"
    sheet.write_text("sample_id,fastq_1,fastq_2\nA,a.cram,\nB,b.bam,\n")
    report = check(samplesheet=str(sheet), reads_dir=str(tmp_path), reference=str(REF38))
    infos = [f for f in report.all_findings() if f.check_id == "REF003"]
    assert len(infos) == 2
    assert any("CRAM" in f.message for f in infos)
    assert report.exit_code in (1, 2)  # SS007 flags the broken BAM; REF003 itself is only a note


def test_cross_checks_skipped_with_reason_when_no_bams(tmp_path: Path) -> None:
    report = check(reference=str(REF38))
    reasons = {s.check_id: s.reason for s in report.skipped}
    assert {"REF001", "REF002", "REF003"} <= set(reasons)
    assert all("no BAM files" in r for r in reasons.values())


def test_ref001_grammar_for_one_chromosome(tmp_path: Path) -> None:
    refs = {f"chr{k}": v for k, v in GRCH38_LENGTHS.items()} | {"chrM": 16569}
    refs["chr21"] += 5
    report = _run(tmp_path, refs)
    msg = next(x.message for x in report.all_findings() if x.check_id == "REF001")
    assert "1 chromosome has a different length" in msg


def test_ref001_grammar_for_several_chromosomes(tmp_path: Path) -> None:
    report = _run(tmp_path, {f"chr{k}": v for k, v in GRCH37_LENGTHS.items()})
    msg = next(x.message for x in report.all_findings() if x.check_id == "REF001")
    assert "chromosomes have different lengths" in msg


def test_ref002_does_not_overstate(tmp_path: Path) -> None:
    report = _run(tmp_path, {"chr1": 248956422})
    msg = next(x.message for x in report.all_findings() if x.check_id == "REF002")
    assert "Current GATK and DeepVariant accept this" in msg
    assert "stop on this mismatch" not in msg
