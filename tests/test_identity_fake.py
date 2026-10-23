"""Identity checks (ID001-ID005) driven by a fake somalier, so they run on any machine.

The fake writes whatever relatedness table a test asks for; the real binary is exercised in
``test_identity_real.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ngs_preflight.context import Declared
from ngs_preflight.errors import PreflightError
from ngs_preflight.identity.run import declared_from_sheet, write_ped
from ngs_preflight.identity.somalier import (
    SomalierRunner,
    parse_pairs_tsv,
    parse_samples_tsv,
    read_somalier_sample_id,
    rewrite_somalier_sample_id,
    split_command,
)
from ngs_preflight.models import Report
from ngs_preflight.samplesheet import parse_samplesheet_text
from tests.helpers import (
    PAIRS_HEADER,
    SAMPLES_HEADER,
    check,
    ids,
    install_fake_somalier,
    make_bam,
    pairs_row,
    samples_row,
)

SHEET = (
    "sample_id,fastq_1,fastq_2,sex,family_id,paternal_id,maternal_id\n"
    "kid,k_R1.fastq.gz,k_R2.fastq.gz,male,F,dad,mum\n"
    "dad,d_R1.fastq.gz,d_R2.fastq.gz,male,F,,\n"
    "mum,m_R1.fastq.gz,m_R2.fastq.gz,female,F,,\n"
)
ID_CHECKS = {"ID001", "ID002", "ID003", "ID004", "ID005"}


def _somalier_files(tmp: Path, names: list[str]) -> list[str]:
    out = []
    for n in names:
        p = tmp / f"{n}.somalier"
        p.write_bytes(bytes([4, len(n)]) + n.encode() + b"\0" * 8)
        out.append(str(p))
    return out


def _sheet(tmp: Path, text: str = SHEET) -> Path:
    p = tmp / "sheet.csv"
    p.write_text(text)
    return p


def _run(
    tmp: Path, samples: list[str], pairs: list[str], sheet: str = SHEET, **cfg: object
) -> Report:
    config = {
        "extract_names": {},
        "samples_tsv": SAMPLES_HEADER + "".join(samples),
        "pairs_tsv": PAIRS_HEADER + "".join(pairs),
        **cfg,
    }
    cmd = install_fake_somalier(tmp, config)
    return check(
        samplesheet=str(_sheet(tmp, sheet)),
        identity=True,
        somalier_cmd=cmd,
        identity_inputs=_somalier_files(tmp, ["kid", "dad", "mum"]),
    )


GOOD_SAMPLES = [samples_row("kid", "1"), samples_row("dad", "1"), samples_row("mum", "2")]
GOOD_PAIRS = [
    pairs_row("kid", "dad", 0.5),
    pairs_row("kid", "mum", 0.49),
    pairs_row("dad", "mum", 0.01),
]


def test_clean_family_passes(tmp_path: Path) -> None:
    report = _run(tmp_path, GOOD_SAMPLES, GOOD_PAIRS)
    assert not ids(report) & ID_CHECKS
    identity = next(f for f in report.files if f.path == "sample identity")
    assert set(identity.checks_run) == ID_CHECKS


def test_id001_duplicate(tmp_path: Path) -> None:
    pairs = [
        pairs_row("kid", "dad", 0.99),
        pairs_row("kid", "mum", 0.49),
        pairs_row("dad", "mum", 0.0),
    ]
    report = _run(tmp_path, GOOD_SAMPLES, pairs)
    assert "ID001" in ids(report)


def test_id002_wrong_parent(tmp_path: Path) -> None:
    pairs = [
        pairs_row("kid", "dad", 0.02),
        pairs_row("kid", "mum", 0.5),
        pairs_row("dad", "mum", 0.0),
    ]
    report = _run(tmp_path, GOOD_SAMPLES, pairs)
    f = next(x for x in report.all_findings() if x.check_id == "ID002")
    assert '"dad" is the father of "kid"' in f.message
    assert "0.02" in f.message


def test_id003_unexpected_relatives(tmp_path: Path) -> None:
    sheet = SHEET + "other,o_R1.fastq.gz,o_R2.fastq.gz,female,G,,\n"
    samples = [*GOOD_SAMPLES, samples_row("other", "2")]
    pairs = [*GOOD_PAIRS, pairs_row("other", "mum", 0.45), pairs_row("kid", "other", 0.25)]
    report = _run(tmp_path, samples, pairs, sheet=sheet)
    msgs = [f.message for f in report.all_findings() if f.check_id == "ID003"]
    assert len(msgs) == 2


def test_id004_sex_mismatch(tmp_path: Path) -> None:
    samples = [samples_row("kid", "2"), samples_row("dad", "1"), samples_row("mum", "2")]
    report = _run(tmp_path, samples, GOOD_PAIRS)
    f = next(x for x in report.all_findings() if x.check_id == "ID004")
    assert 'says "kid" is male' in f.message and "look female" in f.message


def test_id004_unknown_inferred_sex_is_quiet(tmp_path: Path) -> None:
    samples = [samples_row("kid", "0"), samples_row("dad", "1"), samples_row("mum", "2")]
    assert "ID004" not in ids(_run(tmp_path, samples, GOOD_PAIRS))


def test_id005_too_few_sites(tmp_path: Path) -> None:
    samples = [
        samples_row("kid", "1", hom_ref=100, het=50, hom_alt=20),
        samples_row("dad", "1"),
        samples_row("mum", "2"),
    ]
    report = _run(tmp_path, samples, GOOD_PAIRS)
    f = next(x for x in report.all_findings() if x.check_id == "ID005")
    assert '"kid"' in f.message and "170" in f.message


def test_skipped_when_somalier_missing(tmp_path: Path) -> None:
    report = check(
        samplesheet=str(_sheet(tmp_path)),
        identity=True,
        somalier_cmd="definitely-not-somalier-xyz",
        identity_inputs=_somalier_files(tmp_path, ["kid"]),
    )
    skipped = [s for s in report.skipped if s.check_id.startswith("ID")]
    assert len(skipped) == 5
    assert all("not available" in s.reason and "was not found" in s.reason for s in skipped)


def test_skipped_when_no_inputs(tmp_path: Path) -> None:
    cmd = install_fake_somalier(tmp_path, {})
    report = check(samplesheet=str(_sheet(tmp_path)), identity=True, somalier_cmd=cmd)
    assert any("no files were given" in s.reason for s in report.skipped)


def test_skipped_when_relate_fails(tmp_path: Path) -> None:
    report = _run(tmp_path, GOOD_SAMPLES, GOOD_PAIRS, relate_fail=True)
    assert any("relate failed" in s.reason and "exploded" in s.reason for s in report.skipped)
    report = _run(tmp_path, GOOD_SAMPLES, GOOD_PAIRS, relate_no_output=True)
    assert any("did not write" in s.reason for s in report.skipped)


def test_bam_input_needs_sites_and_extract_errors(tmp_path: Path) -> None:
    cmd = install_fake_somalier(tmp_path, {"extract_fail": True})
    bam = make_bam(tmp_path / "kid.bam", {"chr1": 100})
    sheet = str(_sheet(tmp_path))
    report = check(samplesheet=sheet, identity=True, somalier_cmd=cmd, identity_inputs=[str(bam)])
    assert any("sites file is needed" in s.reason for s in report.skipped)
    sites = tmp_path / "sites.vcf.gz"
    sites.write_bytes(b"x")
    report = check(
        samplesheet=sheet,
        identity=True,
        somalier_cmd=cmd,
        identity_inputs=[str(bam)],
        sites=str(sites),
    )
    assert any("could not read kid.bam" in s.reason for s in report.skipped)


def test_extract_then_relate_with_bam(tmp_path: Path) -> None:
    config = {
        "extract_names": {},
        "samples_tsv": SAMPLES_HEADER + "".join(GOOD_SAMPLES),
        "pairs_tsv": PAIRS_HEADER + "".join(GOOD_PAIRS),
    }
    cmd = install_fake_somalier(tmp_path, config)
    inputs = [str(make_bam(tmp_path / f"{n}.bam", {"chr1": 100})) for n in ("kid", "dad", "mum")]
    sites = tmp_path / "sites.vcf.gz"
    sites.write_bytes(b"x")
    report = check(
        samplesheet=str(_sheet(tmp_path)),
        identity=True,
        somalier_cmd=cmd,
        sites=str(sites),
        fasta=str(sites),
        identity_inputs=inputs,
    )
    assert not [s for s in report.skipped if s.check_id.startswith("ID")]
    assert not ids(report) & ID_CHECKS


def test_bad_identity_inputs(tmp_path: Path) -> None:
    cmd = install_fake_somalier(tmp_path, {})
    sheet = str(_sheet(tmp_path))
    with pytest.raises(PreflightError, match="not found"):
        check(
            identity=True,
            somalier_cmd=cmd,
            identity_inputs=[str(tmp_path / "x.bam")],
            samplesheet=sheet,
        )
    txt = tmp_path / "x.txt"
    txt.write_text("x")
    with pytest.raises(PreflightError, match="cannot use"):
        check(identity=True, somalier_cmd=cmd, identity_inputs=[str(txt)], samplesheet=sheet)


def test_somalier_name_roundtrip(tmp_path: Path) -> None:
    src = Path(_somalier_files(tmp_path, ["HG002"])[0])
    assert read_somalier_sample_id(src) == "HG002"
    dst = tmp_path / "copy.somalier"
    rewrite_somalier_sample_id(src, dst, "HG002_again")
    assert read_somalier_sample_id(dst) == "HG002_again"
    assert dst.read_bytes().endswith(b"\0" * 8)
    assert read_somalier_sample_id(tmp_path / "missing") is None
    (tmp_path / "short").write_bytes(b"\x04")
    assert read_somalier_sample_id(tmp_path / "short") is None


def test_tsv_parsers(tmp_path: Path) -> None:
    s = tmp_path / "x.samples.tsv"
    s.write_text(SAMPLES_HEADER + samples_row("a", "2") + samples_row("b", "-9"))
    samples = parse_samples_tsv(s)
    assert samples["a"].inferred_sex == "female"
    assert samples["b"].inferred_sex == "unknown"
    assert samples["a"].informative_sites == 9000 + 5000 + 2500
    p = tmp_path / "x.pairs.tsv"
    p.write_text(PAIRS_HEADER + pairs_row("a", "b", 0.5))
    pairs = parse_pairs_tsv(p)
    assert pairs[0].relatedness == 0.5 and pairs[0].n == 16500


def test_runner_available_branches(tmp_path: Path) -> None:
    assert SomalierRunner("").available()[0] is False
    ok, info = SomalierRunner(install_fake_somalier(tmp_path, {})).available()
    assert ok and info == "0.3.5"
    not_somalier = f'"{sys.executable}" -c "print(1)"'
    ok, info = SomalierRunner(not_somalier).available()
    assert not ok and "did not behave like somalier" in info


def test_declared_and_ped(tmp_path: Path) -> None:
    declared = declared_from_sheet(parse_samplesheet_text(SHEET))
    assert declared["kid"].father == "dad" and declared["dad"].father is None
    assert declared["mum"].sex == "female"
    assert declared_from_sheet(None) == {}
    ped = tmp_path / "x.ped"
    assert write_ped(declared, {"kid", "dad"}, ped)
    assert ped.read_text().splitlines()[0].split("\t") == ["F", "kid", "dad", "0", "1", "-9"]
    assert not write_ped(declared, set(), ped)
    assert write_ped({"z": Declared("z", None, None, None, None)}, {"z"}, ped)


def test_split_command_keeps_windows_backslashes() -> None:
    sep = chr(92)  # a backslash
    exe = f"C:{sep}tools{sep}somalier.exe"
    assert split_command(f'"{exe}" extract', windows=True) == [exe, "extract"]
    assert split_command(exe, windows=True) == [exe]
    assert split_command("docker run --rm img somalier", windows=False)[0] == "docker"
