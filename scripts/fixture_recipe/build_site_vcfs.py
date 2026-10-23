"""Step 2 of the identity-fixture recipe: one single-sample VCF per person with a genotype at
every somalier site, ready for ``somalier extract``.

Inputs (working directory): sites.hg38.vcf.gz; vcf/<sample>.vcf.gz (+ .tbi), the GIAB v4.2.1
GRCh38 benchmark VCFs; xycall.<sample>.vcf.gz from xy_genotypes.sh. Needs bcftools on PATH.
Output: site_vcfs/<sample>.vcf (bgzip and tabix them, then run ``somalier extract``).

A benchmark VCF lists variants only, and somalier treats a site that is missing from a VCF as
unknown, which gives meaningless relatedness. So every site gets a genotype: the benchmark
genotype where the benchmark has the same alleles, otherwise hom-ref (an assumption outside the
benchmark's confident regions). chrX and chrY come from the BAM calls, because the benchmark has
no chrX.
"""

from __future__ import annotations

import gzip
import subprocess
from pathlib import Path

SAMPLES = ("HG002", "HG003", "HG004")


def norm(gt: str) -> str:
    if gt in ("1/1", "1|1"):
        return "1/1"
    if gt in ("0/1", "1/0", "0|1", "1|0"):
        return "0/1"
    return "0/0"


def main() -> None:
    sites = []
    with gzip.open("sites.hg38.vcf.gz", "rt") as handle:
        for line in handle:
            if line[0] != "#":
                f = line.split("\t")
                sites.append((f[0], f[1], f[3], f[4]))
    Path("site_vcfs").mkdir(exist_ok=True)
    for s in SAMPLES:
        query = subprocess.run(
            [
                "bcftools",
                "query",
                "-R",
                "sites.hg38.vcf.gz",
                "-f",
                "%CHROM\t%POS\t%REF\t%ALT[\t%GT]\n",
                f"vcf/{s}.vcf.gz",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        bench = {}
        for line in query.splitlines():
            c, p, r, a, g = line.split("\t")
            bench[(c, p, r, a)] = norm(g)
        xy = {}
        with gzip.open(f"xycall.{s}.vcf.gz", "rt") as handle:
            for line in handle:
                if line[0] != "#":
                    f = line.split("\t")
                    xy[(f[0], f[1])] = norm(f[9].split(":")[0])
        with open(f"site_vcfs/{s}.vcf", "w", newline="\n") as out:
            out.write(
                '##fileformat=VCFv4.2\n##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">\n'
            )
            out.write(f"#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t{s}\n")
            for c, p, r, a in sites:
                gt = xy.get((c, p)) if c in ("chrX", "chrY") else bench.get((c, p, r, a), "0/0")
                out.write(f"{c}\t{p}\t.\t{r}\t{a}\t.\t.\t.\tGT\t{gt or '0/0'}\n")


if __name__ == "__main__":
    main()
