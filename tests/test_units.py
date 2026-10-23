"""Unit tests for the low-level readers: contigs, references, BAM headers, gzip, BED parsing."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from ngs_preflight import gzcheck
from ngs_preflight.bam import BamError, has_bgzf_eof, read_bam_header
from ngs_preflight.bed import merge_intervals, parse_bed_text, read_bed
from ngs_preflight.contigs import (
    GRCH37_LENGTHS,
    GRCH38_LENGTHS,
    add_chr,
    detect_build,
    is_alt_like,
    naming_style,
    strip_chr,
    suggest_rename,
)
from ngs_preflight.errors import PreflightError
from ngs_preflight.fastq import mate_marker, read_names
from ngs_preflight.gzcheck import check_gzip
from ngs_preflight.reference import load_reference, parse_dict, parse_fai
from tests.conftest import REF37, REF38
from tests.helpers import bgzf_block, make_bam


def test_chr_helpers() -> None:
    assert strip_chr("chr1") == "1"
    assert strip_chr("chrM") == "MT"
    assert add_chr("1") == "chr1"
    assert add_chr("MT") == "chrM"
    assert add_chr("M") == "chrM"
    assert add_chr("chr2") == "chr2"
    assert add_chr("GL000207.1") == "GL000207.1"
    assert is_alt_like("chr1_KI270706v1_random")
    assert not is_alt_like("chrX")


def test_naming_style() -> None:
    assert naming_style(["chr1", "chr2"]) == "chr"
    assert naming_style(["1", "2"]) == "plain"
    assert naming_style(["chr1", "2"]) == "mixed"
    assert naming_style(["HLA-A*01:01"]) == "unknown"


def test_suggest_rename() -> None:
    assert suggest_rename("1", ["chr1"]) == "chr1"
    assert suggest_rename("chr1", ["1"]) == "1"
    assert suggest_rename("chr1", ["chr1"]) is None


def test_detect_build() -> None:
    assert detect_build(GRCH38_LENGTHS) == "GRCh38"
    assert detect_build({f"chr{k}": v for k, v in GRCH37_LENGTHS.items()}) == "GRCh37"
    assert detect_build({"chr1": 5}) is None


def test_reference_loaders(tmp_path: Path) -> None:
    assert parse_fai("chr1\t100\t6\t60\t61\n\nchr2\t50\t1\t60\t61\n") == {"chr1": 100, "chr2": 50}
    with pytest.raises(PreflightError):
        parse_fai("chr1\tx\n")
    assert parse_dict("@HD\tVN:1.0\n@SQ\tSN:chr1\tLN:100\tM5:abc\n") == {"chr1": 100}
    d = tmp_path / "ref.dict"
    d.write_text("@HD\tVN:1.0\n@SQ\tSN:chr1\tLN:100\n")
    assert load_reference(d).source == "dict"
    ref = load_reference(REF38)
    assert ref.lengths["chr1"] == 248956422
    assert ref.order["chr1"] == 0
    assert load_reference(REF37).lengths["1"] == 249250621


def test_reference_errors(tmp_path: Path) -> None:
    with pytest.raises(PreflightError, match="not found"):
        load_reference(tmp_path / "missing.fai")
    (tmp_path / "x.fa").write_text(">a\nAC\n")
    with pytest.raises(PreflightError, match=r"\.fai"):
        load_reference(tmp_path / "x.fa")
    (tmp_path / "x.fa.fai").write_text("a\t2\t3\t2\t3\n")
    assert load_reference(tmp_path / "x.fa").lengths == {"a": 2}
    (tmp_path / "empty.fai").write_text("")
    with pytest.raises(PreflightError, match="no contigs"):
        load_reference(tmp_path / "empty.fai")
    (tmp_path / "junk.fai").write_text("this is not a fai\n")
    with pytest.raises(PreflightError):
        load_reference(tmp_path / "junk.fai")


def test_bam_header_roundtrip(tmp_path: Path) -> None:
    bam = make_bam(tmp_path / "a.bam", {"chr1": 1000, "chr2": 500}, samples=("S1", "S2"))
    header = read_bam_header(bam)
    assert header.references == {"chr1": 1000, "chr2": 500}
    assert header.samples == ["S1", "S2"]
    assert has_bgzf_eof(bam)
    assert not has_bgzf_eof(make_bam(tmp_path / "b.bam", {"chr1": 1}, eof=False))


def test_bam_header_errors(tmp_path: Path) -> None:
    p = tmp_path / "bad.bam"
    p.write_bytes(b"not gzip")
    with pytest.raises(BamError):
        read_bam_header(p)
    p.write_bytes(bgzf_block(b"SAM\x01" + b"\0" * 20))
    with pytest.raises(BamError, match="magic"):
        read_bam_header(p)
    p.write_bytes(bgzf_block(b"BAM\x01"))
    with pytest.raises(BamError):
        read_bam_header(p)
    import struct

    p.write_bytes(bgzf_block(b"BAM\x01" + struct.pack("<i", -5)))
    with pytest.raises(BamError, match="plausible"):
        read_bam_header(p)
    p.write_bytes(bgzf_block(b"BAM\x01" + struct.pack("<i", 0) + struct.pack("<i", -1)))
    with pytest.raises(BamError, match="plausible"):
        read_bam_header(p)
    p.write_bytes(
        bgzf_block(b"BAM\x01" + struct.pack("<i", 0) + struct.pack("<i", 1) + struct.pack("<i", 0))
    )
    with pytest.raises(BamError, match="plausible"):
        read_bam_header(p)


def test_gzip_checks(tmp_path: Path) -> None:
    good = tmp_path / "g.gz"
    good.write_bytes(gzip.compress(b"hello\n" * 1000))
    res = check_gzip(good)
    assert res.ok and res.verified_fully

    empty = tmp_path / "e.gz"
    empty.write_bytes(b"")
    assert "empty" in check_gzip(empty).problem

    plain = tmp_path / "p.gz"
    plain.write_text("just text")
    assert "not gzip" in check_gzip(plain).problem

    trunc = tmp_path / "t.gz"
    trunc.write_bytes(good.read_bytes()[:-20])
    assert not check_gzip(trunc).ok

    junk_after = tmp_path / "j.gz"
    junk_after.write_bytes(good.read_bytes() + b"garbage")
    assert not check_gzip(junk_after).ok

    assert not check_gzip(tmp_path / "missing.gz").ok

    bg = tmp_path / "b.bgz"
    bg.write_bytes(bgzf_block(b"data") + gzcheck.BGZF_EOF)
    assert check_gzip(bg).ok
    bg_trunc = tmp_path / "bt.bgz"
    bg_trunc.write_bytes(bgzf_block(b"data"))
    assert "end-of-file" in check_gzip(bg_trunc).problem


def test_gzip_large_file_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gzcheck, "FULL_VERIFY_LIMIT", 10)
    good = tmp_path / "g.gz"
    good.write_bytes(gzip.compress(b"hello\n" * 1000))
    res = check_gzip(good)
    assert res.ok and not res.verified_fully
    corrupt = tmp_path / "c.gz"
    data = bytearray(gzip.compress(b"x" * 5000))
    data[15] ^= 0xFF
    corrupt.write_bytes(bytes(data))
    assert not check_gzip(corrupt).ok


def test_gzip_member_ending_at_chunk_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two members; the first ends one byte before a read-chunk boundary (a split gzip magic)."""
    first = gzip.compress(b"a" * 100, mtime=0)
    second = gzip.compress(b"b" * 100, mtime=0)
    monkeypatch.setattr(gzcheck, "_CHUNK", len(first) + 1)
    p = tmp_path / "multi.gz"
    p.write_bytes(first + second)
    res = check_gzip(p)
    assert res.ok, res.problem
    p.write_bytes(first + second + b"\x1f")  # one stray byte at the very end
    assert not check_gzip(p).ok


def test_fastq_helpers(tmp_path: Path) -> None:
    fq = tmp_path / "a.fastq.gz"
    fq.write_bytes(gzip.compress(b"@r1/1\nAC\n+\nII\n@r2 1:N:0\nAC\n+\nII\n"))
    assert read_names(fq, 2) == ["r1", "r2"]
    assert mate_marker("S1_R1_001.fastq.gz") == ("S1_R#_001", "1")
    assert mate_marker("S1_R2_001.fastq.gz") == ("S1_R#_001", "2")
    assert mate_marker("sample.fastq.gz") is None
    assert mate_marker("sample_R1_part-1.fastq.gz") == ("sample_R#_part-1", "1")
    assert mate_marker("sample_R2_part-1.fastq.gz") == ("sample_R#_part-1", "2")


def test_bed_parsing_details(tmp_path: Path) -> None:
    text = "﻿track name=x\n# c\nchr1 10 20 a\r\nchr1\t30\t40\t b \nchr1\tx\t5\nchr2\t5\n"
    bed = parse_bed_text(text.encode("utf-8"))
    assert bed.has_bom
    assert len(bed.intervals) == 2
    assert len(bed.problems) == 2
    assert bed.crlf_lines and bed.space_delimited_lines
    assert merge_intervals([(1, 5), (5, 8), (20, 30)]) == [(1, 8), (20, 30)]
    gz = tmp_path / "t.bed.gz"
    gz.write_bytes(gzip.compress(b"chr1\t1\t2\n"))
    assert len(read_bed(gz).intervals) == 1
    with pytest.raises(PreflightError):
        read_bed(tmp_path / "nope.bed")
