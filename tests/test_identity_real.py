"""Identity checks against real somalier output for the GIAB Ashkenazim trio.

Needs the somalier binary: put it on PATH, or set PREFLIGHT_SOMALIER_CMD, for example
``docker run --rm -v /tmp:/tmp -v $PWD:$PWD -w $PWD brentp/somalier:v0.3.5 somalier`` (paths must
be mounted at the same location inside the container). Skipped when somalier is unavailable.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from ngs_preflight.identity.somalier import SomalierRunner
from tests.conftest import ROOT
from tests.helpers import check

DATA = ROOT / "tests" / "data" / "identity"
# Read at import time: the autouse fixture in conftest clears the variable inside each test.
SOMALIER_CMD = os.environ.get("PREFLIGHT_SOMALIER_CMD")
_AVAILABLE, _INFO = SomalierRunner(SOMALIER_CMD).available()

somalier = pytest.mark.somalier
needs_somalier = pytest.mark.skipif(not _AVAILABLE, reason=f"somalier not available: {_INFO}")
ID_CHECKS = {"ID001", "ID002", "ID003", "ID004", "ID005"}


def _trio() -> list[Path]:
    return [DATA / f"{s}.somalier" for s in ("HG002", "HG003", "HG004")]


def _findings(sheet: str, extra: tuple[str, ...] = ()) -> dict[str, list[str]]:
    report = check(
        samplesheet=str(DATA / sheet),
        identity=True,
        sites=str(DATA / "sites.hg38.vcf.gz"),
        somalier_cmd=SOMALIER_CMD,
        identity_inputs=[str(p) for p in _trio()] + [str(DATA / e) for e in extra],
    )
    assert not [s for s in report.skipped if s.check_id in ID_CHECKS], report.skipped
    out: dict[str, list[str]] = {}
    for f in report.all_findings():
        if f.check_id in ID_CHECKS:
            out.setdefault(f.check_id, []).append(f.message)
    return out


@pytest.fixture(scope="module")
def observed() -> dict[str, object]:
    return json.loads((DATA / "observed.json").read_text(encoding="utf-8"))  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def relate_result() -> object:
    runner = SomalierRunner(SOMALIER_CMD)
    with tempfile.TemporaryDirectory(prefix="preflight-test-") as tmp:
        return runner.relate(_trio(), DATA / "sites.hg38.vcf.gz", Path(tmp) / "relate")


@somalier
@needs_somalier
def test_trio_relatedness_and_sex_match_the_biology(relate_result: object) -> None:
    result = relate_result  # IdentityResult
    pairs = {
        frozenset((p.sample_a, p.sample_b)): p.relatedness
        for p in result.pairs  # type: ignore[attr-defined]
    }
    assert pairs[frozenset(("HG002", "HG003"))] == pytest.approx(0.5, abs=0.05)  # son / father
    assert pairs[frozenset(("HG002", "HG004"))] == pytest.approx(0.5, abs=0.05)  # son / mother
    assert abs(pairs[frozenset(("HG003", "HG004"))]) < 0.1  # the parents are unrelated
    sex = {k: v.inferred_sex for k, v in result.samples.items()}  # type: ignore[attr-defined]
    assert sex == {"HG002": "male", "HG003": "male", "HG004": "female"}
    for s in result.samples.values():  # type: ignore[attr-defined]
        assert s.informative_sites > 17_000


@somalier
@needs_somalier
def test_recorded_observations_are_still_what_somalier_reports(
    relate_result: object, observed: dict[str, object]
) -> None:
    """observed.json (which docs/identity-fixtures.md is rendered from) matches a fresh run."""
    result = relate_result
    recorded = {(p["a"], p["b"]): p for p in observed["pairs"]}  # type: ignore[attr-defined]
    for p in result.pairs:  # type: ignore[attr-defined]
        rec = recorded[(p.sample_a, p.sample_b)]
        assert p.relatedness == pytest.approx(rec["relatedness"], abs=0.002)
        assert (p.ibs0, p.ibs2, p.n) == (rec["ibs0"], rec["ibs2"], rec["n"])
    for sid, rec in observed["samples"].items():  # type: ignore[attr-defined]
        s = result.samples[sid]  # type: ignore[attr-defined]
        assert (s.n_hom_ref, s.n_het, s.n_hom_alt) == (
            rec["n_hom_ref"],
            rec["n_het"],
            rec["n_hom_alt"],
        )
        assert s.inferred_sex == rec["inferred_sex"]


@somalier
@needs_somalier
def test_true_family_raises_no_identity_findings() -> None:
    assert _findings("trio.csv") == {}


@somalier
@needs_somalier
def test_duplicate_sample_is_id001() -> None:
    found = _findings("trio_duplicate.csv", extra=("HG002_copy.somalier",))
    assert set(found) == {"ID001"}
    assert len(found["ID001"]) == 1
    assert "HG002" in found["ID001"][0] and "HG002_copy" in found["ID001"][0]


@somalier
@needs_somalier
def test_swapped_father_and_son_is_id002_on_the_other_parent() -> None:
    found = _findings("trio_swapped.csv")
    assert set(found) == {"ID002"}
    assert len(found["ID002"]) == 1
    assert 'lists "HG004" as the mother of "HG003"' in found["ID002"][0]


@somalier
@needs_somalier
def test_wrong_declared_sex_is_id004() -> None:
    found = _findings("trio_wrong_sex.csv")
    assert set(found) == {"ID004"}
    assert 'lists "HG002" as female' in found["ID004"][0]


@somalier
@needs_somalier
def test_cli_exit_code_and_output_for_the_swap() -> None:
    env = {**os.environ, "NO_COLOR": "1"}
    if SOMALIER_CMD:
        env["PREFLIGHT_SOMALIER_CMD"] = SOMALIER_CMD
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "ngs_preflight",
            "check",
            "--samplesheet",
            str(DATA / "trio_swapped.csv"),
            "--identity",
            "--sites",
            str(DATA / "sites.hg38.vcf.gz"),
            "--alignments-or-vcfs",
            *map(str, _trio()),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "ID002" in proc.stdout


# --- no somalier needed -------------------------------------------------------------------------


def test_fixture_files_are_real_somalier_files() -> None:
    from ngs_preflight.identity.somalier import read_somalier_sample_id

    for sample in ("HG002", "HG003", "HG004", "HG002_copy"):
        path = DATA / f"{sample}.somalier"
        assert read_somalier_sample_id(path) == sample
        assert 100_000 < path.stat().st_size < 400_000
    total = sum(p.stat().st_size for p in DATA.iterdir())
    assert total < 5_000_000  # the repository stays small


def test_identity_fixtures_doc_is_current() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "record_identity_observations.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
