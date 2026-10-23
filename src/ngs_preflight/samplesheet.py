"""Sample-sheet schema (YAML, validated by pydantic) and a tolerant CSV/TSV reader."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from ngs_preflight.errors import PreflightError


class ColumnSpec(BaseModel):
    name: str
    required: bool
    description: str


class SampleIdRule(BaseModel):
    pattern: str
    max_length: int


class SexVocabulary(BaseModel):
    male: list[str]
    female: list[str]
    unknown: list[str]

    def classify(self, value: str) -> str | None:
        """Return male/female/unknown, or None if the value is not in the vocabulary."""
        v = value.strip().lower()
        for label in ("male", "female", "unknown"):
            if v in getattr(self, label):
                return label
        return None


class SamplesheetSchema(BaseModel):
    columns: list[ColumnSpec]
    sample_id: SampleIdRule
    sex: SexVocabulary
    no_parent_markers: list[str]

    @property
    def required(self) -> list[str]:
        return [c.name for c in self.columns if c.required]

    @property
    def known(self) -> list[str]:
        return [c.name for c in self.columns]


@lru_cache(maxsize=1)
def load_schema() -> SamplesheetSchema:
    text = (resources.files("ngs_preflight") / "schema" / "samplesheet.yaml").read_text("utf-8")
    return SamplesheetSchema.model_validate(yaml.safe_load(text))


class SampleRow(BaseModel):
    """One row of the sheet. Values are kept as text; checks decide what is acceptable."""

    model_config = ConfigDict(extra="allow")

    line: int
    sample_id: str = ""
    fastq_1: str = ""
    fastq_2: str = ""
    sex: str = ""
    family_id: str = ""
    paternal_id: str = ""
    maternal_id: str = ""
    library_id: str = ""
    lane: str = ""


@dataclass
class SampleSheet:
    path: str
    header: list[str] = field(default_factory=list)
    rows: list[SampleRow] = field(default_factory=list)
    delimiter: str = ","
    empty: bool = False

    def has_column(self, name: str) -> bool:
        return name in self.header


def _normalise(name: str) -> str:
    return re.sub(r"[\s\-]+", "_", name.strip().lower())


def near_miss(header: list[str], wanted: str) -> str | None:
    """A header that is probably meant to be ``wanted`` (different case, spaces, hyphens)."""
    for h in header:
        if h != wanted and _normalise(h) == wanted:
            return h
    return None


def parse_samplesheet_text(text: str, path: str = "<memory>") -> SampleSheet:
    if text.startswith("﻿"):
        text = text[1:]
    sheet = SampleSheet(path=path)
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    if not first:
        sheet.empty = True
        return sheet
    sheet.delimiter = "\t" if first.count("\t") > first.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=sheet.delimiter)
    header_seen = False
    for row in reader:
        if not row or all(not c.strip() for c in row):
            continue
        if not header_seen:
            sheet.header = [c.strip() for c in row]
            header_seen = True
            continue
        values = {
            h: (row[i].strip() if i < len(row) else "") for i, h in enumerate(sheet.header) if h
        }
        sheet.rows.append(SampleRow.model_validate({**values, "line": reader.line_num}))
    return sheet


def read_samplesheet(path: str | Path) -> SampleSheet:
    p = Path(path)
    if not p.is_file():
        raise PreflightError(f"sample sheet not found: {p}")
    try:
        text = p.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise PreflightError(f"cannot read sample sheet {p}: {exc}") from exc
    return parse_samplesheet_text(text, str(path))
