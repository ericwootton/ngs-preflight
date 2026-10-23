# JSON report

`preflight check --format json` writes a machine-readable report for pipelines and dashboards.
The formal JSON Schema is [`report.schema.json`](report.schema.json), generated from the same
pydantic models the tool uses, so it cannot drift from the output.

## Versioning

The `schema_version` field is `"MAJOR.MINOR"`. New optional fields increase MINOR; renamed,
removed or re-typed fields increase MAJOR. A consumer should check the major version and ignore
fields it does not know. The current version is `1.0`.

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

- `status`: `pass`, `warnings` or `errors`. With `--strict`, warnings produce `errors`.
- `exit_code`: the process exit code: 0 pass, 1 errors, 2 warnings only. Exit code 3 (tool or usage
  error) means no report was written.
- `files[].kind`: `bed`, `samplesheet`, `reference`, `reads` or `identity`. The `reference` entry
  also carries cross-file findings, and the `identity` entry (named `sample identity`) holds the
  identity checks.
- `findings[].severity`: `ERROR`, `WARN` or `INFO`. `INFO` never changes the exit code.
- `skipped`: checks that could not run, each with a plain-language `reason`. A skipped check is
  not a pass.
- `duration_seconds` is `null` when the environment variable `SOURCE_DATE_EPOCH` is set, which
  also fixes `generated_at`, so that reports can be reproduced byte for byte.

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
