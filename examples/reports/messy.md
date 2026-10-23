# Preflight report: ✖ FAIL

**Fix 8 errors before submitting (and 7 warnings to review).**

8 errors, 7 warnings, 1 note. 20 checks run, 3 skipped.

| File | Type | Errors | Warnings | Notes | Result |
|---|---|---:|---:|---:|---|
| `examples/reference/GRCh38_no_alt_analysis_set.fa.fai` | Reference | 0 | 0 | 0 | – N/A |
| `examples/messy/targets.bed` | Target regions (BED) | 1 | 5 | 1 | ✖ FAIL |
| `examples/messy/samples.csv` | Sample sheet | 7 | 2 | 0 | ✖ FAIL |

## `examples/messy/targets.bed`

### ERROR BED003: Chromosome names exist in the reference

**What this means.** 5 chromosome names in the BED file cannot be found in the reference sequence: "7", "1", "17", "X", "2". The reference uses the "chr" prefix (for example "chr7"), so this looks like a naming difference rather than missing data. Tools will fail or skip these regions, so data you expect to be analysed would be missing.

**How to fix.** Run: preflight fix-bed --add-chr targets.bed --out targets.fixed.bed  (writes a corrected copy and leaves your original untouched).

<details><summary>Technical detail</summary>

All contig names in column 1 are checked against sequence names in the reference .fai/.dict using case-sensitive exact matching. If adding or removing the 'chr' prefix (including MT <-> chrM) resolves all unmatched names, the message states this and suggests running 'preflight fix-bed'.

Evidence: 10 intervals affected. Counts per name: 7=1, 1=5, 17=2, X=1, 2=1

</details>

### WARN BED005: Intervals are sorted

**What this means.** The BED file is not sorted: some intervals start before the interval above them. Some commonly used tools (bedtools, tabix, and many variant callers) require sorted regions. If regions are not sorted, these tools will stop running or quietly return incorrect results.

**How to fix.** Run preflight fix-bed --sort <file> --out <sorted file>. To sort in reference sequence order, add --reference.

<details><summary>Technical detail</summary>

Sorted means that each chromosome forms a single continuous block and start positions within each block do not decrease. These blocks follow reference sequence order (if a reference sequence is specified) or simple alphabetical order (the order produced by 'sort -k1,1 -k2,2n').

Evidence: 1 interval out of place.

</details>

### WARN BED006: No overlapping or touching intervals

**What this means.** 1 interval overlaps an earlier interval and 1 interval touches the previous one end to end. Summing the recorded intervals gives a total target size of 2,579 bp, while coverage after merging overlaps is only 2,539 bp (10 regions become 8). When overlaps are present, coverage can be counted more than once, and some tools may report the same region twice.

**How to fix.** Run preflight fix-bed --merge <file> --out <merged file>, or remove duplicates manually.

<details><summary>Technical detail</summary>

Intervals are sorted per chromosome. An interval overlaps if it starts before the furthest end seen so far. If its start position exactly matches that end position, the intervals are adjacent at their endpoints (book-ended). As in `bedtools merge`, merged territory is calculated after merging overlapping and book-ended intervals.

Evidence: overlapping=1, touching=1, raw_bp=2579, merged_bp=2539

</details>

### WARN BED008: Clean file formatting

**What this means.** 10 lines end with Windows line endings (CRLF). Linux tools treat the invisible carriage return as part of the last column, which breaks sorting, merging and name matching.

**How to fix.** Convert to Unix line endings (LF). Run: preflight fix-bed <file> --out <clean file> to write a cleaned copy.

<details><summary>Technical detail</summary>

Looks for UTF-8 byte order marks, CRLF (Windows) line endings, spaces used as column delimiters, and trailing spaces or tabs. Since the parser accepts all 4 cases, the remaining checks are still run on the cleaned content.

Evidence: First lines: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10

</details>

### WARN BED010: Interval sizes are plausible for a capture panel

**What this means.** 1 interval is shorter than 20 bp. Extremely short regions often result from input errors where the start and end positions are nearly identical. Extremely long regions typically result from accidentally pasting an entire gene or chromosome. These types of regions behave differently from standard capture targets.

**How to fix.** Check the listed lines. If they are intended (for example, a large linkage region), you can ignore this warning. Otherwise, correct them.

<details><summary>Technical detail</summary>

Flags intervals shorter than 20 bp and those longer than 1,000,000 bp (1 Mb). For designs targeting the whole genome or large regions, you can ignore this warning.

Evidence: Short, lines: 8

</details>

### WARN BED011: Interval names are unique

**What this means.** 1 name is used for more than one interval (for example, "TGT_001" is used 2 times). Since results are typically reported by name, duplicate names may cause these results to be merged or overwritten.

**How to fix.** Ensure that names are unique (for example, by adding exon numbers). Alternatively, if duplicate names are intentional, ignore this warning.

<details><summary>Technical detail</summary>

This check is only performed when column 4 (name) is present. Empty names and the placeholder '.' are ignored. Different exons of the same gene often use the same name, and this is acceptable in some cases.

Evidence: Repeated: TGT_001 x2

</details>

### INFO BED009: Territory summary

**What this means.** 10 intervals on 5 chromosomes, covering 2,539 bp after merging overlaps. Sizes: smallest 8 bp, median 290 bp, largest 330 bp. chrY absent; chrM absent.

**What to do.** No action is required. Confirm that the totals match the expected values for your design (for example, the panel or exome you ordered).

<details><summary>Technical detail</summary>

Counts intervals, total base pairs, base pairs after merging, and size distribution. Counts intervals on alt/decoy/unplaced contigs (contigs whose names do not match chr1-22, X, Y, or M, regardless of whether they include 'chr'). Also records whether chrY and chrM are present and the number of ignored header lines.

Evidence: intervals=10, raw_bp=2579, merged_bp=2539, mean_size=257.9, style=plain

</details>

## `examples/messy/samples.csv`

### ERROR SS002: Sample IDs are unique

**What this means.** 1 sample ID appears on more than one row without a different lane number (for example, "S01" on lines 2, 4). 2 different samples with the same ID cannot be distinguished, and their results would be merged or overwritten.

**How to fix.** Assign a unique ID to each sample. If the same sample was sequenced across multiple lanes, add a lane column and assign the corresponding lane number to each row.

<details><summary>Technical detail</summary>

The same sample_id is allowed in multiple rows only if a 'lane' column is present. In these rows, lane values must be non-empty and distinct (i.e. the same sample is sequenced across multiple lanes). All other cases are considered duplicates.

Evidence: Duplicated: S01 (lines 2, 4)

</details>

### ERROR SS003: Sample IDs use safe characters

**What this means.** 1 sample ID is not allowed (for example, "S 05/b"). Sample IDs may contain only letters, digits, underscores, and hyphens, up to 64 characters. Spaces, slashes, and other symbols cause problems with file names and many workflow tools.

**How to fix.** Change sample names using only A-Z, a-z, 0-9, underscores (_), and hyphens (-).

<details><summary>Technical detail</summary>

Schema pattern is ^[A-Za-z0-9_-]+$ and the maximum length is 64. Empty IDs are reported by SS001 and are not reported here.

Evidence: Lines: 5

</details>

### ERROR SS004: Read files exist and are readable

**What this means.** 2 files listed in the sample sheet could not be found or opened (for example, "S10_R1.fastq.gz" for sample "S10"). The run would fail as soon as it tried to read them.

**How to fix.** Check the file names for spelling errors, and confirm that the files have been copied to the folder specified by --reads-dir. Upload any missing files.

<details><summary>Technical detail</summary>

Relative paths are resolved against --reads-dir, while absolute paths are used as provided. Paths expressed as URLs (s3://, gs://, https://, ...) are skipped because they cannot be validated. Files with a size of 0 bytes are considered unreadable.

Evidence: Looked in: examples/messy/reads. S10_R1.fastq.gz (S10): not found; S10_R2.fastq.gz (S10): not found

</details>

### ERROR SS005: No file is listed twice

**What this means.** 1 file is listed more than once (for example, "S01_R1.fastq.gz", used by S01 (line 2) and S11 (line 11)). Reads from one file would be counted under several samples, or the same reads would be used as both read 1 and read 2.

**How to fix.** Check that each sample references its own files. If you created a new row by copying another row, update the file names in that row.

<details><summary>Technical detail</summary>

Paths are compared in their recorded form after slash normalization. If the same file appears in 2 rows or in both fastq_1 and fastq_2 within 1 row, this is reported.

Evidence: S01_R1.fastq.gz: S01 (line 2), S11 (line 11)

</details>

### ERROR SS008: Sex values are from the allowed list

**What this means.** 1 value is not in the list of allowed values (for example, "banana" for sample "S06"). Downstream steps and the sex check need a recognised value.

**How to fix.** Use male, female, or unknown (or M, F, U, or 1, 2, 0), or leave the cell blank.

<details><summary>Technical detail</summary>

Accepted values are male/m/1, female/f/2, and unknown/u/0/NA/n/a/'.' (case-insensitive). A blank value is also allowed and indicates unknown sex. This vocabulary is defined in src/ngs_preflight/schema/samplesheet.yaml.

Evidence: Lines: 6

</details>

### ERROR SS009: Family relationships are consistent

**What this means.** 1 sample is listed as its own parent (for example "S07" as its own father, line 7). The pedigree is used for relatedness checks and by analyses which take the pedigree into account, so an inconsistent pedigree can give incorrect results.

**How to fix.** Add a row for each parent (if a parent is not included in this submission, leave the corresponding parent cell blank). Also confirm that no individual is listed as their own parent.

<details><summary>Technical detail</summary>

Every non-empty paternal_id / maternal_id must match the sample_id in another row, and no sample may be its own father or mother. Blank values, 0, '.', NA, n/a, and none indicate no parent record.

Evidence: Lines: 7

</details>

### ERROR SS009: Family relationships are consistent

**What this means.** 2 parent references point to a sample that is not in the sheet (for example "S01" names "S03" as its mother, line 2). The pedigree is used for relatedness checks and by analyses which take the pedigree into account, so an inconsistent pedigree can give incorrect results.

**How to fix.** Add a row for each parent (if a parent is not included in this submission, leave the corresponding parent cell blank). Also confirm that no individual is listed as their own parent.

<details><summary>Technical detail</summary>

Every non-empty paternal_id / maternal_id must match the sample_id in another row, and no sample may be its own father or mother. Blank values, 0, '.', NA, n/a, and none indicate no parent record.

Evidence: line 2: S01 -> S03 (mother); line 7: S07 -> S99 (mother)

</details>

### WARN SS006: Read 1 and read 2 files pair up

**What this means.** 2 rows do not look like matching read 1 / read 2 pairs (for example, sample "S08": fastq_1 looks like read 2 and fastq_2 like read 1 (swapped)). Mispaired files make alignment fail or produce meaningless results, often only after hours of computation.

**How to fix.** Confirm that fastq_1 contains the read 1 file and fastq_2 contains the read 2 file. Check that these files came from the same sequencing run and that neither has been renamed or swapped.

<details><summary>Technical detail</summary>

File names are compared after R1/R2 (or _1/_2) is replaced with a placeholder. If both files are readable (--reads-dir), the first 100 read names are compared. This comparison uses the first token of each header and ignores a trailing /1 or /2. Files without an R1/R2 marker pass the name test.

Evidence: line 8 S08: fastq_1 looks like read 2 and fastq_2 like read 1 (swapped); line 11 S11: the two file names differ by more than R1/R2

</details>

### WARN SS007: Compressed files are intact

**What this means.** 1 file appears damaged or incomplete (for example, "S09_R1.fastq.gz": the compressed data ends unexpectedly (the file looks truncated)). An interrupted download or copy is the usual cause, and it makes runs fail partway through.

**How to fix.** Copy or download the file again, and compare its checksum (for example, md5sum) with the checksum provided by the sender.

<details><summary>Technical detail</summary>

This is a quick check and does not provide full validation. For every .gz/.bam file, it checks the gzip signature and the header, and that the first 4 MiB can be decompressed. BGZF files (.bam, bgzip FASTQ) must contain the 28-byte end-of-file marker. Other gzip files of 32 MiB or less are decompressed in full and their CRC is verified. Larger non-BGZF gzip files cannot be shown to be complete at low cost, so only their beginning and end are checked.

Evidence: 17 file(s) checked. S09_R1.fastq.gz: the compressed data ends unexpectedly (the file looks truncated)

</details>

## Skipped checks

- **REF001** Reference, BED and reads agree on naming and genome build (`examples/reference/GRCh38_no_alt_analysis_set.fa.fai`): there are no BAM files to compare (FASTQ files carry no chromosome header, and BAMs are only found when --reads-dir and the sample sheet point at them)
- **REF002** Reads and reference list the same chromosomes (`examples/reference/GRCh38_no_alt_analysis_set.fa.fai`): there are no BAM files to compare (FASTQ files carry no chromosome header, and BAMs are only found when --reads-dir and the sample sheet point at them)
- **REF003** Read-file header could not be inspected (`examples/reference/GRCh38_no_alt_analysis_set.fa.fai`): there are no BAM files to compare (FASTQ files carry no chromosome header, and BAMs are only found when --reads-dir and the sample sheet point at them)

*ngs-preflight 0.1.0, generated 2026-01-01T00:00:00Z.*
