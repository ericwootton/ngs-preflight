"""Data models shared by the checks, the runner and the report writers.

The JSON report is a serialisation of :class:`Report`; changing these models is
a change to the public JSON contract and must bump ``SCHEMA_VERSION``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"


class Severity(StrEnum):
    """How serious a finding is. ERROR blocks submission; WARN should be reviewed."""

    ERROR = "ERROR"
    WARN = "WARN"
    INFO = "INFO"

    @property
    def rank(self) -> int:
        return {"ERROR": 0, "WARN": 1, "INFO": 2}[self.value]


FileKind = Literal["bed", "samplesheet", "reference", "reads", "identity"]
Status = Literal["pass", "warnings", "errors"]


class Finding(BaseModel):
    """One problem (or note) found by one check in one file."""

    model_config = ConfigDict(frozen=True)

    check_id: str = Field(description="Stable check identifier, e.g. BED003.")
    severity: Severity
    title: str = Field(description="Short name of the check.")
    file: str = Field(description="The file (or pseudo-file) this finding belongs to.")
    message: str = Field(
        description="Plain-language explanation: what is wrong and why it matters."
    )
    fix: str = Field(description="Plain-language suggestion for putting it right.")
    detail: str = Field(description="Technical description of how the check works.")
    technical: str = Field(
        default="", description="Instance-specific evidence (line numbers, examples, counts)."
    )


class SkippedCheck(BaseModel):
    """A check that could not run, with the reason in plain language."""

    check_id: str
    title: str
    file: str | None = None
    reason: str


class FileResult(BaseModel):
    """Everything known about one input file."""

    path: str
    kind: FileKind
    checks_run: list[str] = Field(default_factory=list)
    checks_passed: list[str] = Field(
        default_factory=list, description="Checks that ran and found nothing to report."
    )
    findings: list[Finding] = Field(default_factory=list)


class Summary(BaseModel):
    errors: int = 0
    warnings: int = 0
    infos: int = 0
    files: int = 0
    checks_run: int = 0
    checks_skipped: int = 0


class ToolInfo(BaseModel):
    name: str = "ngs-preflight"
    version: str


class Report(BaseModel):
    """The complete result of one ``preflight check`` run (the JSON contract)."""

    schema_version: str = Field(default=SCHEMA_VERSION, description="Version of this JSON layout.")
    tool: ToolInfo
    generated_at: str = Field(description="UTC timestamp, ISO 8601.")
    duration_seconds: float | None = Field(
        default=None, description="Wall-clock run time; null in reproducible-output mode."
    )
    strict: bool = Field(description="True if warnings were treated as errors.")
    status: Status = Field(
        description="Overall outcome after applying --strict: pass, warnings or errors."
    )
    exit_code: int = Field(description="The process exit code that goes with this outcome.")
    headline: str = Field(description="One-sentence plain-language verdict.")
    summary: Summary
    files: list[FileResult]
    skipped: list[SkippedCheck] = Field(default_factory=list)

    def all_findings(self) -> list[Finding]:
        return [f for fr in self.files for f in fr.findings]
