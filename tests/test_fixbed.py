"""``preflight fix-bed``: corrected copies, never in-place edits."""

from __future__ import annotations

from pathlib import Path

import pytest

from ngs_preflight.bed import parse_bed_text
from ngs_preflight.errors import PreflightError
from ngs_preflight.fixbed import FixOptions, fix_bed, write_fixed
from ngs_preflight.reference import load_reference
from tests.conftest import REF38

RAW = b"1\t500\t600\ta\n1\t100\t200\tb\n2\t10\t20\tc\nMT\t1\t5\td\n"


def test_add_chr_and_sort() -> None:
    lines, summary = fix_bed(parse_bed_text(RAW), FixOptions(add_chr=True, sort=True))
    assert lines[0].startswith("chr1\t100\t200")
    assert lines[-1].startswith("chrM\t")
    assert summary.renamed[("1", "chr1")] == 2
    assert summary.sorted_applied and summary.moved >= 1


def test_strip_chr_notes_unchangeable() -> None:
    bed = parse_bed_text(b"chr1\t1\t5\nchrUn_x\t1\t5\n")
    lines, summary = fix_bed(bed, FixOptions(strip_chr=True))
    assert lines[0].startswith("1\t")
    assert "chrM" not in lines[0]
    assert summary.unchanged_contigs == []
    lines, summary = fix_bed(parse_bed_text(b"1\t1\t5\nGL000.1\t1\t5\n"), FixOptions(add_chr=True))
    assert summary.unchanged_contigs == ["GL000.1"]


def test_sort_uses_reference_order() -> None:
    bed = parse_bed_text(b"chr10\t1\t5\nchr2\t1\t5\nchr1\t1\t5\n")
    lines, _ = fix_bed(bed, FixOptions(sort=True, reference=load_reference(REF38)))
    assert [ln.split("\t")[0] for ln in lines] == ["chr1", "chr2", "chr10"]
    lines, _ = fix_bed(bed, FixOptions(sort=True))
    assert [ln.split("\t")[0] for ln in lines] == ["chr1", "chr10", "chr2"]


def test_merge_drops_names_and_reports_bp() -> None:
    bed = parse_bed_text(b"chr1\t1\t10\ta\nchr1\t5\t20\tb\nchr1\t20\t30\tc\nchr2\t1\t4\td\n")
    lines, summary = fix_bed(bed, FixOptions(merge=True))
    assert lines == ["chr1\t1\t30", "chr2\t1\t4"]
    assert summary.merged_before == 4 and summary.merged_after == 2
    assert summary.bp_before > summary.bp_after


def test_cleanup_reported() -> None:
    raw = b"\xef\xbb\xbfchr1 1 5 x \r\nchr1\t6\t9\n"
    lines, summary = fix_bed(parse_bed_text(raw), FixOptions())
    assert lines == ["chr1\t1\t5\tx", "chr1\t6\t9"]
    text = " ".join(summary.cleanup)
    assert "byte-order mark" in text and "Unix endings" in text and "tabs" in text


def test_refuses_unreadable_and_conflicting() -> None:
    with pytest.raises(PreflightError, match="cannot be read"):
        fix_bed(parse_bed_text(b"chr1\tx\t5\n"), FixOptions())
    with pytest.raises(PreflightError, match="together"):
        fix_bed(parse_bed_text(RAW), FixOptions(add_chr=True, strip_chr=True))
    with pytest.raises(PreflightError, match="--merge"):
        fix_bed(parse_bed_text(b"chr1\t9\t5\n"), FixOptions(merge=True))


def test_write_never_overwrites(tmp_path: Path) -> None:
    src = tmp_path / "t.bed"
    src.write_bytes(RAW)
    dst, summary = write_fixed(src, None, FixOptions(add_chr=True))
    assert dst.name == "t.fixed.bed"
    assert src.read_bytes() == RAW
    assert "was not changed" in summary.lines(str(src), str(dst))[0]
    with pytest.raises(PreflightError, match="already exists"):
        write_fixed(src, dst, FixOptions())
    write_fixed(src, dst, FixOptions(), force=True)
    with pytest.raises(PreflightError, match="refusing to overwrite the input"):
        write_fixed(src, src, FixOptions(), force=True)
    assert src.read_bytes() == RAW


def test_gz_output_is_real_gzip(tmp_path: Path) -> None:
    import gzip

    src = tmp_path / "t.bed"
    src.write_bytes(RAW)
    dst, _ = write_fixed(src, tmp_path / "out.bed.gz", FixOptions(add_chr=True))
    assert gzip.decompress(dst.read_bytes()).startswith(b"chr1\t500")


def test_refuses_same_file_even_with_different_spelling(tmp_path: Path) -> None:
    src = tmp_path / "t.bed"
    src.write_bytes(RAW)
    alias = tmp_path / "." / "t.bed"  # the same file, spelled differently
    with pytest.raises(PreflightError, match="refusing to overwrite the input"):
        write_fixed(src, alias, FixOptions(), force=True)
    assert src.read_bytes() == RAW
