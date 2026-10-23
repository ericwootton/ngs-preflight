# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). A version bump regenerates `docs/checks.md`
(`preflight docs`); a test fails if the committed file is out of date.

## [0.1.0] - 2026-10-22

First release: the core checks, four report formats and the optional identity checks.

### Added

- `preflight check`: runs every applicable check on a target BED, a sample sheet and a reference
  (`.fai` or `.dict`), and compares them with each other and with BAM headers.
  Exit codes: 0 pass, 1 errors, 2 warnings only, 3 tool or usage error; `--strict` makes warnings
  count as errors.
- 11 BED checks (BED001-BED011): readability, coordinates, contig names, contigs' lengths,
  sort order, overlaps, a heuristic for 1-based coordinates, formatting problems, a territory
  summary, interval sizes and duplicate names.
- 9 sample-sheet checks (SS001-SS009): required columns, unique and safe sample IDs, read files
  that exist, duplicated files, R1/R2 pairing, gzip integrity, sex vocabulary and family links.
- 3 reference-compatibility checks (REF001-REF003): naming style and genome build, missing
  contigs, and a note when a read-file header could not be inspected (for example CRAM).
- 5 optional identity checks (ID001-ID005) that wrap `somalier`: duplicated samples, parent-child
  relatedness, unexpected relatives, declared versus inferred sex, and too few informative sites.
  They are skipped, with a plain-language reason, when somalier is not available.
- Reports: terminal text (rich), JSON (documented, versioned schema), Markdown and a single
  self-contained HTML file.
- `preflight explain <ID>`, `preflight fix-bed` (writes a corrected copy, never edits in place)
  and `preflight docs` (generates `docs/checks.md` and `docs/report.schema.json`).
- A Dockerfile (runs as root, so WDL engines can pass it their inputs), a pre-commit configuration and a GitHub Actions workflow.
- A documentation site (MkDocs, published to GitHub Pages by `.github/workflows/docs.yml`) with
  the check catalogue and the example reports; `preflight explain` links to the catalogue entry.
- Examples: a "good" and a "messy" submission with generated reports in `examples/reports/`.
- Real somalier fixtures for the GIAB trio HG002, HG003 and HG004, and the engineered failures
  built from them (`docs/identity-fixtures.md`). relate is run without a pedigree, because with
  one somalier echoes the pedigree's sex instead of inferring it; when somalier makes no sex call
  (VCF input has no read depth) the sex is taken from chrX heterozygosity.
