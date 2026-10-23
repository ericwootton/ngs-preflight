# Preflight report: ✔ PASS

**Ready to run.**

0 errors, 0 warnings, 1 note. 20 checks run, 3 skipped.

| File | Type | Errors | Warnings | Notes | Result |
|---|---|---:|---:|---:|---|
| `examples/reference/GRCh38_no_alt_analysis_set.fa.fai` | Reference | 0 | 0 | 0 | – N/A |
| `examples/good/targets.bed` | Target regions (BED) | 0 | 0 | 1 | ✔ PASS |
| `examples/good/samples.csv` | Sample sheet | 0 | 0 | 0 | ✔ PASS |

## `examples/good/targets.bed`

### INFO BED009: Territory summary

**What this means.** 18 intervals on 7 chromosomes, covering 5,646 bp after merging overlaps. Sizes: smallest 231 bp, median 300 bp, largest 700 bp. chrY absent; chrM present.

**What to do.** No action is required. Confirm that the totals match the expected values for your design (for example, the panel or exome you ordered).

<details><summary>Technical detail</summary>

Counts intervals, total base pairs, base pairs after merging, and size distribution. Counts intervals on alt/decoy/unplaced contigs (contigs whose names do not match chr1-22, X, Y, or M, regardless of whether they include 'chr'). Also records whether chrY and chrM are present and the number of ignored header lines.

Evidence: intervals=18, raw_bp=5646, merged_bp=5646, mean_size=313.7, style=chr

</details>

## Skipped checks

- **REF001** Reference, BED and reads agree on naming and genome build (`examples/reference/GRCh38_no_alt_analysis_set.fa.fai`): there are no BAM files to compare (FASTQ files carry no chromosome header, and BAMs are only found when --reads-dir and the sample sheet point at them)
- **REF002** Reads and reference list the same chromosomes (`examples/reference/GRCh38_no_alt_analysis_set.fa.fai`): there are no BAM files to compare (FASTQ files carry no chromosome header, and BAMs are only found when --reads-dir and the sample sheet point at them)
- **REF003** Read-file header could not be inspected (`examples/reference/GRCh38_no_alt_analysis_set.fa.fai`): there are no BAM files to compare (FASTQ files carry no chromosome header, and BAMs are only found when --reads-dir and the sample sheet point at them)

*ngs-preflight 0.1.0, generated 2026-01-01T00:00:00Z.*
