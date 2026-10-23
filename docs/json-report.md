# JSON report

`preflight check --format json` exports a machine-readable report for pipelines and
dashboards. The official JSON Schema is [`report.schema.json`](report.schema.json) and is
generated from the same pydantic models used by the tool. This prevents it from drifting from
the output.

## Versioning

The `schema_version` field is `"MAJOR.MINOR"`. Adding an optional field increases MINOR.
Renaming a field, removing a field, or changing a field's type increases MAJOR. Consumers
should check the major version and ignore fields they do not recognize. The current version is
`1.0`.

## Shape

```json
{
  "schema_version": "1.0",
  "tool": {"name": "ngs-preflight", "version": "0.1.0"},
  "generated_at": "2026-01-01T00:00:00Z",
  "duration_seconds": 0.12,
  "strict": false,
  "status": "errors",
  "exit_code": 1,
  "headline": "Fix 2 errors before submitting",
  "summary": {"errors": 2, "warnings": 0, "infos": 1, "files": 3,
              "checks_run": 20, "checks_skipped": 3},
  "files": [
    {
      "path": "targets.bed",
      "kind": "bed",
      "checks_run": ["BED001", "BED002"],
      "checks_passed": ["BED001"],
      "findings": [
        {
          "check_id": "BED002",
          "severity": "ERROR",
          "title": "Start and end make sense",
          "file": "targets.bed",
          "message": "Plain-language description of this occurrence.",
          "fix": "What to do about it.",
          "detail": "How the check works (the same for every occurrence).",
          "technical": "Evidence from this file, such as line numbers."
        }
      ]
    }
  ],
  "skipped": [
    {"check_id": "BED003", "title": "Chromosome names exist in the reference",
     "file": "targets.bed", "reason": "no reference was given (use --reference)"}
  ]
}
```

## Fields

- `status` is `pass`, `warnings`, or `errors`. When `--strict` is specified, warning results become `errors`.
- `exit_code`: Process exit code. 0 indicates a pass, 1 indicates errors, and 2 indicates warnings
  only. Exit code 3 (tool or usage error) indicates that no report was written.
- `files[].kind` is `bed`, `samplesheet`, `reference`, `reads`, or `identity`. `reference`
  entries also include findings from cross-file checks, while `identity` entries (named
  `sample identity`) hold the identity checks.
- `findings[].severity` is `ERROR`, `WARN`, or `INFO`. `INFO` never changes the exit code.
- `skipped` indicates checks which could not be executed. Each entry includes a `reason`
  written in plain language. These checks are not considered passed.
- If the environment variable `SOURCE_DATE_EPOCH` is set, `duration_seconds` is `null` and
  `generated_at` is also fixed. This allows the report to be reproduced byte for byte.

## Reading it from a script

```bash
preflight check --samplesheet samples.csv --format json --out report.json
python - <<'PY'
import json
report = json.load(open("report.json"))
assert report["schema_version"].split(".")[0] == "1"
for file in report["files"]:
    for f in file["findings"]:
        print(f["severity"], f["check_id"], file["path"], f["message"])
PY
```
