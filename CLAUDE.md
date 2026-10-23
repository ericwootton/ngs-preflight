# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository.

## What this project is

`ngs-preflight` checks the input target BED file, sample sheet, and reference sequence before
sequencing analysis begins. It can optionally use somalier to check sample identity. This is
intended to turn problems which would otherwise appear hours into a run (or never appear) into
short, plain-language messages. These messages explain the problem and how to correct it. This
is a general-purpose tool. Keep it general.

Coverage includes file format and consistency checks, human-readable reports, and
reports for pipelines. Variant calling, sequence alignment, clinical
interpretation, and anything which requires network access are excluded.

## Layout

- `src/ngs_preflight/checks/`: Each check group corresponds to 1 module. Each check is a
  function decorated with `@check(...)` from `registry.py`. This decorator stores the ID,
  severity, title, message template, technical details, and suggested fixes. `docs/checks.md`
  is generated from this information.
- `src/ngs_preflight/report/`: Text, JSON, Markdown, and HTML renderers based on a single pydantic `Report`.
- `src/ngs_preflight/identity/` is a wrapper for somalier. Everything else is implemented in pure Python.
- `tests/data/`: 1 fixture was created manually for each failure mode. Each fixture is accompanied by `*.expected.json`.

## Conventions

- Type-annotated Python 3.11+ code passes `mypy --strict` without errors. `ruff` is used for linting and formatting (line length 100).
- Runtime dependencies remain minimal and include only pydantic v2, rich, jinja2, and pyyaml. No dependencies require compilation.
- Messages are intended for laboratory staff, not programmers. Use short sentences to explain what
  each message means and what action should be taken. Message and correction text are templates
  which incorporate values from `Hit.params`. Check the grammar for 1 item and for multiple items.
- Each check includes at least 1 positive fixture and 1 negative fixture.
- Every number appearing in the documentation is generated programmatically and is never
  typed. `docs/checks.md`, `docs/report.schema.json`, and `examples/reports/*` are
  generated using `preflight docs` and `python scripts/build_examples.py`. Tests will
  fail if these files are not kept up to date.
- Never edit the user's files in place. Output any modified files as new files.
- The check for 1-based coordinates (BED007) is heuristic. Its message must state this
  explicitly, and the check must not produce a message for the "good" example.
- For the somalier fixture, use the actual tool output as the source of truth. Do not manually edit `.somalier` files. `tests/data/identity/observed.json` and `docs/identity-fixtures.md` are regenerated using `scripts/record_identity_observations.py` (requires somalier).

## Running things

```bash
python -m pip install -e ".[dev]"
python -m pytest                      # everything except tests that need somalier runs by default
python -m pytest -m somalier          # real somalier (PREFLIGHT_SOMALIER_CMD or a binary on PATH)
python -m ruff check . && python -m ruff format --check .
python -m mypy --strict src
python -m ngs_preflight docs          # regenerate docs/checks.md and docs/report.schema.json
python scripts/build_examples.py      # regenerate examples/ and examples/reports/
# docs site: docs/examples/ is gitignored and filled at build time, as in docs.yml
mkdir -p docs/examples && cp examples/reports/{good,messy}.html docs/examples/
mkdocs build --strict
```

CI runs the same commands in Python 3.11, 3.12, and 3.13 environments (and on Windows). It
requires 90% line coverage for `checks/` and runs somalier tests within the `brentp/somalier`
container.

## Review rule

Changes created by Claude are reviewed and tested before they are committed. Use conventional
commit messages (`feat:`, `fix:`, `docs:`, `test:`, `chore:`). Even if only 1 person is working,
work on a branch and create a pull request to keep the CI history visible.
