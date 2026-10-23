# How to prepare your BED file and sample sheet

This page is intended for people who send us data. Following this page avoids the most
common reasons submissions are returned. You can use `preflight check` to check your files
in about 1 minute (see the end of this page).

## 1. The target BED file (your capture regions)

A BED file lists the genomic regions to be analyzed, and 1 line corresponds to 1 region.

**Format.** Plain text containing 3 TAB-separated columns for chromosome, start position, and
end position. An optional name can be specified in column 4.

```text
chr1	1000	1300	exon_1
chr1	5000	5400	exon_2
```

**Do**

- Use chromosome names which match those in the reference sequence. If chromosome 1 is represented
  as `chr1` in the reference sequence, do not write `1`. Use `chr1` instead. The mitochondrial
  chromosome is represented as `chrM` in one naming convention and `MT` in another.
- Use the same genome build as the reads and reference sequence (for example, GRCh38).
  Coordinates from GRCh37 refer to different positions in GRCh38.
- Use the 0-based, half-open coordinates specified by the BED standard. The first base of a
  chromosome is at position 0, and the interval excludes the end position. A region covering the
  first 100 bases is `0  100`. Coordinates from tools which output 1-based positions (many
  spreadsheets, UCSC tables, and VCF position fields) require conversion. Subtract 1 from the
  start position.
- Sort the file using chromosome as the primary sort key and start position as the secondary sort key (`sort -k1,1 -k2,2n`).
- Merge overlapping regions, or tell us why they overlap.
- Use Unix line endings (LF) and save as UTF-8 plain text.

**Avoid**

- Header lines other than `track`, `browser`, or `#` comments.
- Spaces used in place of TAB, trailing spaces, byte order marks (invisible characters added by
  Excel at the start of a file), and Windows (CRLF) line endings.
- Regions which extend beyond the end of a chromosome or have an end position less than the start position.
- Using Excel or Word for editing. If you must use a spreadsheet, export it as tab-delimited text.

**Fix common problems automatically.** `preflight fix-bed targets.bed --add-chr --sort` writes a
corrected copy (`targets.fixed.bed`) and lists the changes. It never modifies the original file.
To remove the prefix instead of adding it, use `--strip-chr`. To merge overlapping regions, use
`--merge`.

## 2. The sample sheet

A CSV (comma-separated) or TSV (tab-separated) file with a header row and 1 row per pair of
sequencing read files.

| Column | Required | What to put |
|---|---|---|
| `sample_id` | yes | A unique name for the sample. Letters, digits, `_` and `-` only, up to 64 characters. No spaces or slashes. |
| `fastq_1` | yes | File name of read 1 (or of the BAM/CRAM file). |
| `fastq_2` | yes, for FASTQ | File name of read 2. For a BAM or CRAM row, leave it empty or leave the column out. |
| `sex` | no | `male`, `female` or `unknown` (also accepted: M, F, 1, 2, 0). |
| `family_id` | no | A name for the family, if samples are related. |
| `paternal_id`, `maternal_id` | no | The `sample_id` of the father and the mother. Leave empty (or 0) if unknown. |
| `library_id`, `lane` | no | Library name and lane number. Needed if one sample was sequenced more than once. |

**Do**

- Confirm that all files listed in the sample sheet have been uploaded and that their filenames match
  exactly, including case.
- Assign a unique `sample_id` to each sample. For samples sequenced across multiple lanes, you
  may use multiple rows with the same `sample_id`. However, this is only allowed if each row has a
  different `lane`.
- Confirm that read 1 and read 2 are paired. Their names should differ only in the `R1` and `R2` portions.
- If a parent is specified, the sample sheet must also contain a row for that parent.

**Avoid**

- Misspelled column names (`sample id`, `Fastq1`). The checker suggests the closest correct column name.
- Blank cells in required columns and duplicate entries for the same file.
- Files that were truncated during upload. Compare the file size against the original
  file, or run `gzip -t file.fastq.gz`.

## 3. Check your files before sending them

```bash
pipx install ngs-preflight          # or: docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/data" ngs-preflight:0.1.0 preflight ...
preflight check --samplesheet samples.csv --bed targets.bed \
  --reference GRCh38.fa.fai --reads-dir ./fastq --format html --out report.html
```

Open `report.html` in your browser. The report begins with a summary ("Ready to run" or "Fix 2
errors before submitting"). It explains each issue and how to correct it in plain language. Send
us the report along with your files.

- Errors must be corrected. Warnings should be checked. Notes require no action.
- `preflight explain BED003` explains any check in detail.
- If you do not have a reference file, ask us for the `.fai` file corresponding to the genome build you are using.
