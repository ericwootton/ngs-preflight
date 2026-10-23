"""JSON report and its JSON Schema (the contract other pipelines consume)."""

from __future__ import annotations

import json
from typing import Any

from ngs_preflight.models import Report


def render_json(report: Report) -> str:
    return report.model_dump_json(indent=2) + "\n"


def report_json_schema() -> dict[str, Any]:
    schema = Report.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "ngs-preflight report"
    return schema


def render_schema() -> str:
    return json.dumps(report_json_schema(), indent=2, sort_keys=True) + "\n"
