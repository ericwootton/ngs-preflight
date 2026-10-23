# Changelog

All notable changes to this project are recorded here. This format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). A version bump regenerates
`docs/checks.md` (`preflight docs`). Tests will fail if the
committed file is not up to date.

## [0.1.0] - 2026-10-22

Initial release includes core checks, 4 report formats, and the optional sample identity checks.

### Added

- `preflight check` runs all applicable checks on the target BED, sample sheet, and reference
  sequence (`.fai` or `.dict`). This compares the inputs against each other and against BAM
  headers. Exit codes are 0 for a pass, 1 for errors, 2 for warnings only, and 3 for tool or
  usage errors. Warnings are treated as errors when `--strict` is specified.
- The 11 BED checks (BED001-BED011) cover readability, coordinates, contig names, contig
  lengths, sort order, overlapping intervals, a heuristic for 1-based coordinates, formatting
  issues, a territory summary, interval sizes, and duplicate names.
- There are 9 sample sheet checks (SS001-SS009). These cover required columns, sample ID
  uniqueness and safety, read file existence, duplicate files, R1/R2 pairing, gzip integrity,
  allowed sex terms, and family relationship links.
- 3 reference sequence compatibility checks (REF001-REF003) cover naming conventions and
  genome build, missing contigs, and notes when read file headers cannot be checked (for
  example, CRAM).
- A wrapper for `somalier` provides 5 optional sample identity checks (ID001-ID005). These cover
  duplicate samples, parent-child relationships, unexpected relatives, comparison of declared and
  inferred sex, and too few informative sites. If somalier is unavailable, these checks are
  skipped and the reason is explained in plain language.
- Reports are available as terminal text (rich), JSON (with a documented, versioned
  schema), Markdown, and a single self-contained HTML file.
- `preflight explain <ID>`, `preflight fix-bed` (writes a copy containing the corrections and
  never edits in place), and `preflight docs` (generates `docs/checks.md` and
  `docs/report.schema.json`).
- A Dockerfile (running as root allows the WDL engine to pass inputs), a pre-commit configuration, and a GitHub Actions workflow.
- A documentation site provides a catalogue of checks and example reports (MkDocs, published to
  GitHub Pages through `.github/workflows/docs.yml`). `preflight explain` links to the
  corresponding entry in the catalogue.
- Examples of good and messy submissions (generated reports are in `examples/reports/`).
- Real somalier fixtures for the GIAB trio HG002, HG003, and HG004, and artificial failure cases
  built from these fixtures (`docs/identity-fixtures.md`). somalier relate is run without supplying
  pedigree information. This is because somalier does not infer sex when pedigree information is
  supplied. It directly reports the sex recorded in the pedigree. When somalier does not assign
  sex (when the VCF input contains no read depth), sex is determined using chrX heterozygosity.
