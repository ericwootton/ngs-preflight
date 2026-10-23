"""Context objects handed to check functions, one per check scope."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ngs_preflight.bam import BamHeader
from ngs_preflight.bed import BedFile
from ngs_preflight.identity.somalier import IdentityResult
from ngs_preflight.reference import Reference
from ngs_preflight.samplesheet import SampleSheet, SamplesheetSchema


@dataclass
class BedContext:
    path: str
    bed: BedFile
    reference: Reference | None = None


@dataclass
class SheetContext:
    path: str
    sheet: SampleSheet
    schema: SamplesheetSchema
    reads_dir: Path | None = None
    pair_sample_size: int = 100

    def resolve(self, value: str) -> Path:
        """Where a path from the sheet lives on disk (relative paths use --reads-dir)."""
        p = Path(value)
        if p.is_absolute() or self.reads_dir is None:
            return p
        return self.reads_dir / p


@dataclass
class ReadsInfo:
    """A reads file referenced by the sheet, with its header if it could be read."""

    path: str
    sample_id: str
    kind: str  # "bam", "cram" or "other"
    header: BamHeader | None = None
    note: str = ""


@dataclass
class CrossContext:
    reference: Reference | None
    reference_path: str | None = None
    expected_build: str | None = None
    bed_files: list[tuple[str, BedFile]] = field(default_factory=list)
    reads: list[ReadsInfo] = field(default_factory=list)


@dataclass
class Declared:
    """What the sample sheet says about one sample."""

    sample_id: str
    sex: str | None = None  # "male", "female" or None (unknown / not given)
    father: str | None = None
    mother: str | None = None
    family: str = ""


@dataclass
class IdentityContext:
    result: IdentityResult
    declared: dict[str, Declared] = field(default_factory=dict)
