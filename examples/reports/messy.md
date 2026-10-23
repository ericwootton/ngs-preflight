# Preflight report: ✖ FAIL

**Fix 8 errors before submitting (and 7 warnings to review).**

8 errors, 7 warnings, 1 notes. 20 checks run, 3 skipped.

| File | Type | Errors | Warnings | Notes | Result |
|---|---|---:|---:|---:|---|
| `examples/reference/GRCh38_no_alt_analysis_set.fa.fai` | Reference | 0 | 0 | 0 | – N/A |
| `examples/messy/targets.bed` | Target regions (BED) | 1 | 5 | 1 | ✖ FAIL |
| `examples/messy/samples.csv` | Sample sheet | 7 | 2 | 0 | ✖ FAIL |

## `examples/messy/targets.bed`

### ERROR BED003: Chromosome names exist in the reference

**What this means.** 5 chromosome names in the BED file cannot be found in the reference: "7", "1", "17", "X", "2". The reference uses the "chr" prefix (for example "chr7"), so this looks like a naming difference rather than missing data. Tools will fail or skip these regions, so the data you expect to be analysed would be missing.

**How to fix.** Run: preflight fix-bed --add-chr targets.bed --out targets.fixed.bed  (writes a corrected copy and leaves your original untouched).

<details><summary>Technical detail</summary>

Every contig name in column 1 is compared, exactly and case-sensitively, with the sequence names in the reference .fai/.dict. If adding or removing a 'chr' prefix (including MT <-> chrM) would make every missing name match, the message says so and points to 'preflight fix-bed'.

Evidence: 10 intervals affected. Counts per name: 7=1, 1=5, 17=2, X=1, 2=1

</details>

### WARN BED005: Intervals are sorted

**What this means.** The BED file is not sorted: some intervals start before the interval above them. Several common tools (bedtools, tabix, many variant callers) need sorted regions and will stop, or quietly give wrong answers, if they are not.

**How to fix.** Run: preflight fix-bed --sort <file> --out <sorted file>. Add --reference to sort in reference order.

<details><summary>Technical detail</summary>

Sorted means every chromosome is one contiguous block, starts do not decrease inside a block, and the blocks follow either the reference order (when a reference is given) or plain alphabetical order (as produced by 'sort -k1,1 -k2,2n').

Evidence: 1 interval out of place.

</details>

### WARN BED006: No overlapping or touching intervals

**What this means.** 1 interval overlaps an earlier interval and 1 interval touches the previous one end to end. Counted as written, the targets add up to 2,579 bp, but they cover only 2,539 bp once overlaps are merged (10 regions become 8). Overlaps can double-count coverage and make some tools report the same region twice.

**How to fix.** Run: preflight fix-bed --merge <file> --out <merged file>, or remove the duplicates by hand.

<details><summary>Technical detail</summary>

Intervals are sorted per chromosome. An interval that starts before the furthest end seen so far overlaps; one that starts exactly at that end is book-ended (touching). Merged territory is computed after joining both kinds, like 'bedtools merge'.

Evidence: overlapping=1, touching=1, raw_bp=2579, merged_bp=2539

</details>

### WARN BED008: Clean file formatting

**What this means.** 10 lines end with Windows line endings (CRLF). Linux tools treat the invisible carriage return as part of the last column, which breaks sorting, merging and name matching.

**How to fix.** Convert to Unix line endings (LF). Run: preflight fix-bed <file> --out <clean file> to write a cleaned copy.

<details><summary>Technical detail</summary>

Looks for a UTF-8 byte-order mark, CRLF (Windows) line endings, spaces used as column separators, and trailing spaces or tabs at the end of a line. The parser tolerates all four, so the other checks still run on the cleaned content.

Evidence: First lines: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10

</details>

### WARN BED010: Interval sizes are plausible for a capture panel

**What this means.** 1 interval is shorter than 20 bp. Very short regions are often typing mistakes (a start and end that are almost equal), and very long ones are usually whole genes or chromosomes pasted in by mistake; neither behaves like normal capture targets.

**How to fix.** Check the listed lines. If they are intended (for example a large linkage region), you can ignore this warning; otherwise correct them.

<details><summary>Technical detail</summary>

Flags intervals shorter than 20 bp and longer than 1,000,000 bp (1 Mb). Whole-genome or large-region designs can ignore this warning.

Evidence: Short, lines: 8

</details>

### WARN BED011: Interval names are unique

**What this means.** 1 name is used for more than one interval (for example "TGT_001", 2 times). Results are often reported per name, so repeated names can be merged together or overwrite each other.

**How to fix.** Make the names unique (for example add an exon number), or ignore this warning if repeated names are intended.

<details><summary>Technical detail</summary>

Only runs when column 4 (name) is present. Empty names and the placeholder '.' are ignored. Repeated names for different exons of one gene are common and may be fine.

Evidence: Repeated: TGT_001 x2

</details>

### INFO BED009: Territory summary

**What this means.** 10 intervals on 5 chromosomes, covering 2,539 bp after merging overlaps. Sizes: smallest 8 bp, median 290 bp, largest 330 bp. chrY absent; chrM absent.

**What to do.** No action needed. Check that the totals match what you expect for your design (for example, the panel or exome you ordered).

<details><summary>Technical detail</summary>

Counts intervals, total and merged base pairs, the size distribution, intervals on alt/decoy/unplaced contigs (any name that is not chr1-22, X, Y or M, with or without 'chr'), presence of chrY and chrM, and the number of header lines that were ignored.

Evidence: intervals=10, raw_bp=2579, merged_bp=2539, mean_size=257.9, style=plain

</details>

## `examples/messy/samples.csv`

### ERROR SS002: Sample IDs are unique

**What this means.** 1 sample ID appears on more than one row without a different lane number (for example "S01" on lines 2, 4). Two different samples with the same ID cannot be told apart, and their results would be merged or overwritten.

**How to fix.** Give every sample a unique ID. If one sample was sequenced on several lanes, add a lane column and give each row its own lane number.

<details><summary>Technical detail</summary>

Rows may repeat a sample_id only when a 'lane' column exists and each repeated row has a distinct, non-blank lane (one sample sequenced on several lanes). Anything else is a duplicate.

Evidence: Duplicated: S01 (lines 2, 4)

</details>

### ERROR SS003: Sample IDs use safe characters

**What this means.** 1 sample ID is not allowed (for example "S 05/b"). Sample IDs may only use letters, digits, underscore and hyphen, up to 64 characters. Spaces, slashes and other symbols break file names and many workflow tools.

**How to fix.** Rename the samples using only A-Z, a-z, 0-9, underscore (_) and hyphen (-).

<details><summary>Technical detail</summary>

Pattern from the schema: ^[A-Za-z0-9_-]+$, maximum length 64. Blank IDs are reported by SS001, not here.

Evidence: Lines: 5

</details>

### ERROR SS004: Read files exist and are readable

**What this means.** 2 files listed in the sample sheet could not be found or opened (for example "S10_R1.fastq.gz" for sample "S10"). The run would fail as soon as it tries to read them.

**How to fix.** Check the file names for typos and that the files were copied to the folder given with --reads-dir. Upload any files that are missing.

<details><summary>Technical detail</summary>

Relative paths are resolved against --reads-dir; absolute paths are used as written. Paths that are URLs (s3://, gs://, https://, ...) cannot be checked and are skipped. A file of 0 bytes counts as unreadable.

Evidence: Looked in: examples\messy\reads. S10_R1.fastq.gz (S10): not found; S10_R2.fastq.gz (S10): not found

</details>

### ERROR SS005: No file is listed twice

**What this means.** 1 file is listed more than once (for example "S01_R1.fastq.gz", used by S01 (line 2) and S11 (line 11)). Reads from one file would be counted under several samples, or the same reads used as both read 1 and read 2.

**How to fix.** Check that each sample points at its own files. If you copied a row to make a new one, update its file names.

<details><summary>Technical detail</summary>

Paths are compared as written (after normalising slashes). A file appearing in two rows, or as both fastq_1 and fastq_2 of one row, is reported.

Evidence: S01_R1.fastq.gz: S01 (line 2), S11 (line 11)

</details>

### ERROR SS008: Sex values are from the allowed list

**What this means.** 1 value is not in the accepted list (for example "banana" for sample "S06"). Downstream steps and the sex check need a recognised value.

**How to fix.** Use one of: male, female, unknown (or M, F, U; or 1, 2, 0), or leave the cell blank.

<details><summary>Technical detail</summary>

Accepted values (case-insensitive): male/m/1, female/f/2, unknown/u/0/NA/n/a/'.'. A blank cell is allowed (sex unknown). The vocabulary is defined in src/ngs_preflight/schema/samplesheet.yaml.

Evidence: Lines: 6

</details>

### ERROR SS009: Family relationships are consistent

**What this means.** 1 sample is listed as its own parent (for example "S07" as its own father, line 7). The family structure is used for relatedness checks and by family-aware analysis, so an inconsistent one can give wrong results.

**How to fix.** Add a row for each parent (or clear the parent cell if the parent is not part of this submission), and make sure nobody is listed as their own parent.

<details><summary>Technical detail</summary>

Every non-empty paternal_id / maternal_id must be the sample_id of another row, and no sample may be its own father or mother. Blank, 0, '.', NA, n/a and none mean 'no parent recorded'.

Evidence: Lines: 7

</details>

### ERROR SS009: Family relationships are consistent

**What this means.** 2 parent references point to a sample that is not in the sheet (for example "S01" names "S03" as its mother, line 2). The family structure is used for relatedness checks and by family-aware analysis, so an inconsistent one can give wrong results.

**How to fix.** Add a row for each parent (or clear the parent cell if the parent is not part of this submission), and make sure nobody is listed as their own parent.

<details><summary>Technical detail</summary>

Every non-empty paternal_id / maternal_id must be the sample_id of another row, and no sample may be its own father or mother. Blank, 0, '.', NA, n/a and none mean 'no parent recorded'.

Evidence: line 2: S01 -> S03 (mother); line 7: S07 -> S99 (mother)

</details>

### WARN SS006: Read 1 and read 2 files pair up

**What this means.** 2 rows do not look like matching read 1 / read 2 pairs (for example sample "S08": fastq_1 looks like read 2 and fastq_2 like read 1 (swapped)). Mispaired files make alignment fail or produce nonsense, often only after hours of compute.

**How to fix.** Check that fastq_1 holds the read 1 file and fastq_2 the read 2 file from the same sequencing run, and that neither was renamed or swapped.

<details><summary>Technical detail</summary>

File names are compared after replacing R1/R2 (or _1/_2) with a placeholder. When both files can be read (--reads-dir), the first 100 read names are compared (the first token of each header, ignoring a trailing /1 or /2). Files without an R1/R2 marker pass the name test.

Evidence: line 8 S08: fastq_1 looks like read 2 and fastq_2 like read 1 (swapped); line 11 S11: the two file names differ by more than R1/R2

</details>

### WARN SS007: Compressed files are intact

**What this means.** 1 file appears damaged or incomplete (for example "S09_R1.fastq.gz": the compressed data ends unexpectedly (the file looks truncated)). A truncated download or interrupted copy is the usual cause, and it makes runs fail partway through.

**How to fix.** Copy or download the file again, and compare its checksum (for example md5sum) with the one given by the sender.

<details><summary>Technical detail</summary>

Fast check, not a full validation. Every .gz/.bam: gzip signature, clean header, first 4 MiB decompresses. BGZF files (.bam, bgzip FASTQ): the 28-byte end-of-file marker must be present. Other gzip files up to 32 MiB: the whole stream is decompressed and its CRC verified. Larger non-BGZF gzip files cannot be proven complete cheaply, so only the head and trailer are checked.

Evidence: 17 file(s) checked. S09_R1.fastq.gz: the compressed data ends unexpectedly (the file looks truncated)

</details>

## Skipped checks

- **REF001** Reference, BED and reads agree on naming and genome build (`examples/reference/GRCh38_no_alt_analysis_set.fa.fai`): there are no BAM files to compare (FASTQ files carry no chromosome header, and BAMs are only found when --reads-dir and the sample sheet point at them)
- **REF002** Reads and reference list the same chromosomes (`examples/reference/GRCh38_no_alt_analysis_set.fa.fai`): there are no BAM files to compare (FASTQ files carry no chromosome header, and BAMs are only found when --reads-dir and the sample sheet point at them)
- **REF003** Read-file header could not be inspected (`examples/reference/GRCh38_no_alt_analysis_set.fa.fai`): there are no BAM files to compare (FASTQ files carry no chromosome header, and BAMs are only found when --reads-dir and the sample sheet point at them)

*ngs-preflight 0.1.0, generated 2026-01-01T00:00:00Z.*
