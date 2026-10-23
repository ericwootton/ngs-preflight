# How to prepare your BED file and sample sheet

This page is for the people who send us data. Following it avoids the most common reasons a
submission is returned. You can check your files yourself, in about a minute, with
`preflight check` (see the end of this page).

## 1. The target BED file (your capture regions)

A BED file lists the regions of the genome you want analysed, one region per line.

**Format.** Plain text with three columns separated by TAB characters: chromosome, start, end.
An optional fourth column is a name.

```text
chr1	1000	1300	exon_1
chr1	5000	5400	exon_2
```

**Do**

- Use the same chromosome names as your reference. If the reference calls the first chromosome
  `chr1`, write `chr1`, not `1`. The mitochondrial chromosome is `chrM` in one naming style and `MT`
  in the other.
- Use the same genome build as your reads and reference (for example GRCh38). Coordinates from
  GRCh37 point to different places in GRCh38.
- Use 0-based, half-open coordinates, which is the BED standard: the first base of a chromosome is
  position 0, and the end is not included. A region covering the first 100 bases is `0  100`.
  Tools that write 1-based coordinates (many spreadsheets, UCSC tables, VCF positions) need
  converting: subtract 1 from the start.
- Sort the file by chromosome and then by start (`sort -k1,1 -k2,2n`).
- Merge overlapping regions, or tell us why they overlap.
- Save as plain UTF-8 text with Unix line endings (LF).

**Avoid**

- Header lines other than `track`, `browser` or `#` comments.
- Spaces instead of TABs, trailing spaces, a byte-order mark (an invisible character that Excel
  adds at the start of a file), and Windows (CRLF) line endings.
- Regions that run past the end of the chromosome, or where the end is smaller than the start.
- Excel or Word as the editor. If you must use a spreadsheet, export as tab-separated text.

**Fix common problems automatically.** `preflight fix-bed targets.bed --add-chr --sort` writes a
corrected copy (`targets.fixed.bed`) and lists what it changed. It never changes your original
file. Use `--strip-chr` to remove the prefix instead, and `--merge` to merge overlaps.

## 2. The sample sheet

One row per pair of read files, as a CSV (comma-separated) or TSV (tab-separated) file with a
header row.

| Column | Required | What to put |
|---|---|---|
| `sample_id` | yes | A unique name for the sample. Letters, digits, `_` and `-` only, up to 64 characters. No spaces or slashes. |
| `fastq_1` | yes | File name of read 1 (or of the BAM/CRAM file). |
| `fastq_2` | yes | File name of read 2. Leave empty only for single-end data or BAM/CRAM. |
| `sex` | no | `male`, `female` or `unknown` (also accepted: M, F, 1, 2, 0). |
| `family_id` | no | A name for the family, if samples are related. |
| `paternal_id`, `maternal_id` | no | The `sample_id` of the father and the mother. Leave empty (or 0) if unknown. |
| `library_id`, `lane` | no | Library name and lane number. Needed if one sample was sequenced more than once. |

**Do**

- Make sure every file named in the sheet is uploaded and that the names match exactly, including
  upper and lower case.
- Give every sample its own `sample_id`. A sample sequenced on several lanes can have several rows
  with the same `sample_id` only if each row has a different `lane`.
- Make sure read 1 and read 2 belong together: the names should differ only by `R1` and `R2`.
- If you give a parent, that parent must also be a row in the sheet.

**Avoid**

- Misspelled column names (`sample id`, `Fastq1`). The checker tells you the closest correct name.
- Blank cells in required columns, and the same file listed twice.
- Files that were cut short during upload. Compare the file size with the original, or run
  `gzip -t file.fastq.gz`.

## 3. Check your files before sending them

```bash
pipx install ngs-preflight          # or: docker run --rm -v "$PWD:/data" ngs-preflight:0.1.0 preflight ...
preflight check --samplesheet samples.csv --bed targets.bed \
  --reference GRCh38.fa.fai --reads-dir ./fastq --format html --out report.html
```

Open `report.html` in a browser. It starts with a summary ("Ready to run" or "Fix 2 errors before
submitting") and explains each problem in plain language, with how to fix it. Send us the report
together with your files.

- Errors must be fixed. Warnings should be looked at. Notes need no action.
- `preflight explain BED003` explains any check in detail.
- If you do not have the reference file, ask us for the `.fai` file for the genome build you used.
