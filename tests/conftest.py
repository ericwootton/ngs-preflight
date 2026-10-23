"""Shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(__file__).parent / "data"
REF38 = ROOT / "examples" / "reference" / "GRCh38_no_alt_analysis_set.fa.fai"
REF37 = DATA / "hs37d5.fa.fai"


@pytest.fixture(scope="session")
def ref38() -> Path:
    return REF38


@pytest.fixture(scope="session")
def ref37() -> Path:
    return REF37


@pytest.fixture(autouse=True)
def _fixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    monkeypatch.delenv("PREFLIGHT_SOMALIER_CMD", raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
