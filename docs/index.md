# ngs-preflight

Before running a sequencing analysis for the first time, check the target BED, sample sheet, and
reference sequence used as inputs. Additionally, you can choose to check whether the samples
match those listed in the sample sheet. Issues and recommended corrections are explained in
plain language so the laboratory or customer can address them without help from a
bioinformatician.

[Example reports](examples.md){ .md-button .md-button--primary }
[Check catalogue](checks.md){ .md-button }
[Source on GitHub](https://github.com/ericwootton/ngs-preflight){ .md-button }

!!! note "Not a clinical tool"
    ngs-preflight checks file formats and consistency between files. It does not validate the
    science or the data quality of a sequencing run.

## Why it exists

Most failed sequencing analyses fail due to subtle problems in their inputs. For example, a
reference sequence uses `chr1` while the BED file uses `1`. A sample sheet lists files which no
one has uploaded, or 2 samples come from the same person. These problems often go unnoticed until
hours of computation or a series of email exchanges have taken place. `ngs-preflight` identifies
such problems in seconds.

## What it checks

| Group | Checks | Examples |
|---|---|---|
| Target BED | BED001-BED011 | unreadable lines, end before start, `1` versus `chr1`, intervals past the contig end, unsorted or overlapping intervals, 1-based coordinates |
| Sample sheet | SS001-SS009 | missing columns, duplicate or unsafe sample IDs, read files that do not exist or are truncated, R1/R2 pairing, unknown sex values, broken family links |
| Reference | REF001-REF003 | contig naming style and genome build, contigs missing from the reference, read-file headers that do not match |
| Identity (optional) | ID001-ID005 | duplicated samples, parent-child pairs that are not related, unexpected relatives, declared versus inferred sex (needs [somalier](https://github.com/brentp/somalier)) |

Each check includes an ID, severity, a plain-language message, technical details, and a
suggested correction. The [catalogue](checks.md) is generated from the code, and
`preflight explain <ID>` prints 1 entry with a link back to the catalogue.

## Install and run

```bash
pipx install git+https://github.com/ericwootton/ngs-preflight     # or: python -m pip install .
preflight check --samplesheet samples.csv --bed targets.bed \
    --reference GRCh38_no_alt_analysis_set.fa.fai --reads-dir reads/ \
    --format html --out preflight.html
preflight explain BED003
```

Or with Docker, without Python:

```bash
docker build -t ngs-preflight:0.1.0 https://github.com/ericwootton/ngs-preflight.git
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/data" ngs-preflight:0.1.0 \
    preflight check --bed targets.bed --reference GRCh38.fa.fai
```

Exit code `0` indicates a pass, while `1` indicates errors (or warnings with `--strict`). Exit
code `2` indicates warnings only, while `3` indicates a tool or usage error. Pipelines can
stop on a nonzero exit code before any compute resources are consumed. This is how the
[wgs-release-validation](https://ericwootton.github.io/wgs-release-validation/) workflow
operates.

## What a report looks like

HTML report for submission materials with intentionally introduced defects:

![HTML report for the messy example showing a summary card, a file table, and initial findings](images/report-messy.png)

Reports are provided as terminal-friendly text, a single self-contained HTML file, Markdown for
tickets, and JSON for pipelines ([schema](json-report.md)).
[Open the full example reports](examples.md).

## For customers

[How to prepare your BED file and sample sheet](for-customers.md) is a 1-page guide which can be
sent unchanged to customers.
