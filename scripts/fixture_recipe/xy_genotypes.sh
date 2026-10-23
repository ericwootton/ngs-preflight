#!/bin/bash
# Step 1 of the identity-fixture recipe: genotype the chrX / chrY somalier sites from the public
# Illumina NovaSeq 35x BAMs of the GIAB Ashkenazim trio (random access, no full download).
# Needs bcftools, bgzip and tabix on PATH. Run in an empty working directory that holds
# sites.hg38.vcf.gz (from https://github.com/brentp/somalier/files/3412456/sites.hg38.vcf.gz) and
# xy.fa (chrX and chrY of GCA_000001405.15_GRCh38_no_alt_analysis_set.fa, indexed with samtools faidx).
# Output: xycall.<sample>.vcf.gz for HG002, HG003, HG004.
set -euo pipefail
B=https://storage.googleapis.com/deepvariant/case-study-testdata
zcat sites.hg38.vcf.gz | awk '$1=="chrX"||$1=="chrY"{print $1"\t"$2"\t"$4","$5}' > xy.tsv
cut -f1,2 xy.tsv > xy.regions
bgzip -f -k xy.tsv && tabix -f -s1 -b2 -e2 xy.tsv.gz
for s in HG002 HG003 HG004; do
  bcftools mpileup -f xy.fa -R xy.regions -a FORMAT/AD,FORMAT/DP -q 20 -Q 20 -d 1000 \
      "$B/$s.novaseq.pcr-free.35x.dedup.grch38_no_alt.bam" -Ou |
    bcftools call -m -C alleles -T xy.tsv.gz -Oz -o "xycall.$s.vcf.gz"
  tabix -f "xycall.$s.vcf.gz"
done
