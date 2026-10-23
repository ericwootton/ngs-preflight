# Example reports

Two example submissions ship with the repository. Both reports below were produced by running
the tool on them (`python scripts/build_examples.py`), with a fixed timestamp so the output is
reproducible. Nothing in them is edited by hand.

| Submission | What is in it | Result | Reports |
|---|---|---|---|
| [`examples/good`](https://github.com/ericwootton/ngs-preflight/tree/main/examples/good) | A trio with a sorted, well-formed BED and matching read files | PASS: "Ready to run" | [HTML](examples/good.html) · [Markdown](https://github.com/ericwootton/ngs-preflight/blob/main/examples/reports/good.md) · [JSON](https://github.com/ericwootton/ngs-preflight/blob/main/examples/reports/good.json) |
| [`examples/messy`](https://github.com/ericwootton/ngs-preflight/tree/main/examples/messy) | The mistakes seen most often in real submissions: `1` instead of `chr1`, unsorted and overlapping intervals, Windows line endings, duplicate and unsafe sample IDs, a missing read file, a truncated gzip, sex values outside the allowed list, broken family links | FAIL, exit code 1 | [HTML](examples/messy.html) · [Markdown](https://github.com/ericwootton/ngs-preflight/blob/main/examples/reports/messy.md) · [JSON](https://github.com/ericwootton/ngs-preflight/blob/main/examples/reports/messy.json) |

The HTML files are single files with no external assets, readable without colour and in dark
mode. They can be attached to a ticket or an email as they are.

To reproduce them:

```bash
preflight check --samplesheet examples/messy/samples.csv --bed examples/messy/targets.bed \
    --reference examples/reference/GRCh38_no_alt_analysis_set.fa.fai \
    --reads-dir examples/messy/reads --format html --out messy.html
```
