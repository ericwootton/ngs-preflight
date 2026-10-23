"""Regenerate the example inputs and the example reports.

    python scripts/build_examples.py            # inputs and reports
    python scripts/build_examples.py --check    # fail if committed files differ from the output

The reports are produced by running the real tool on the example inputs, with a fixed timestamp
(SOURCE_DATE_EPOCH) so the output is reproducible. Nothing in examples/reports is edited by hand.
All coordinates are synthetic: they sit near real gene regions but are not real exons.
"""

from __future__ import annotations

import argparse
import gzip
import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"
REFERENCE = EX / "reference" / "GRCh38_no_alt_analysis_set.fa.fai"
FIXED_EPOCH = "1767225600"  # 2026-01-01T00:00:00Z

# (contig, start, end, name): synthetic, sorted, well separated, 0-based half-open.
GOOD_TARGETS = [
    ("chr1", 11_000, 11_240, "TGT_001"),
    ("chr1", 65_419, 65_650, "TGT_002"),
    ("chr1", 925_900, 926_180, "TGT_003"),
    ("chr1", 930_100, 930_410, "TGT_004"),
    ("chr2", 47_403_000, 47_403_320, "TGT_005"),
    ("chr2", 47_410_150, 47_410_400, "TGT_006"),
    ("chr7", 117_480_000, 117_480_265, "TGT_007"),
    ("chr7", 117_530_900, 117_531_240, "TGT_008"),
    ("chr7", 117_559_500, 117_559_820, "TGT_009"),
    ("chr11", 5_225_400, 5_225_700, "TGT_010"),
    ("chr11", 5_226_700, 5_227_000, "TGT_011"),
    ("chr17", 7_668_500, 7_668_830, "TGT_012"),
    ("chr17", 7_670_600, 7_670_880, "TGT_013"),
    ("chr17", 43_045_700, 43_046_020, "TGT_014"),
    ("chr17", 43_057_000, 43_057_300, "TGT_015"),
    ("chrX", 31_100_000, 31_100_300, "TGT_016"),
    ("chrX", 32_000_000, 32_000_260, "TGT_017"),
    ("chrM", 3_200, 3_900, "TGT_018"),
]

GOOD_SHEET = [
    # sample_id, sex, family, father, mother
    ("FAM1_child", "male", "FAM1", "FAM1_father", "FAM1_mother"),
    ("FAM1_father", "male", "FAM1", "", ""),
    ("FAM1_mother", "female", "FAM1", "", ""),
]


def fastq_bytes(sample: str, mate: int, n: int = 4, truncate: bool = False) -> bytes:
    """A tiny, valid, deterministic gzip FASTQ (a few made-up reads).

    Stored (level 0) deflate blocks, so the bytes do not depend on the zlib build.
    """
    lines = []
    for i in range(1, n + 1):
        seq = "ACGT" * 6 + "TTGCA"[: (i % 5) + 1]
        lines += [
            f"@{sample}:RUN1:1:{1000 + i}:{2000 + 7 * i} {mate}:N:0:1",
            seq,
            "+",
            "I" * len(seq),
        ]
    raw = ("\n".join(lines) + "\n").encode()
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=0) as gz:
        gz.write(raw)
    data = buf.getvalue()
    return data[: len(data) - 12] if truncate else data


def write(path: Path, data: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)


def build_good() -> dict[Path, bytes | str]:
    out: dict[Path, bytes | str] = {}
    bed = "".join(f"{c}\t{s}\t{e}\t{n}\n" for c, s, e, n in GOOD_TARGETS)
    out[EX / "good" / "targets.bed"] = bed
    rows = ["sample_id,fastq_1,fastq_2,sex,family_id,paternal_id,maternal_id,library_id,lane"]
    for sid, sex, fam, dad, mom in GOOD_SHEET:
        rows.append(
            f"{sid},{sid}_R1.fastq.gz,{sid}_R2.fastq.gz,{sex},{fam},{dad},{mom},LIB_{sid},1"
        )
        out[EX / "good" / "reads" / f"{sid}_R1.fastq.gz"] = fastq_bytes(sid, 1)
        out[EX / "good" / "reads" / f"{sid}_R2.fastq.gz"] = fastq_bytes(sid, 2)
    out[EX / "good" / "samples.csv"] = "\n".join(rows) + "\n"
    return out


def build_messy() -> dict[Path, bytes | str]:
    out: dict[Path, bytes | str] = {}
    # BED: plain contig names (reference uses chr), unsorted, overlapping, book-ended, CRLF,
    # one tiny interval, one repeated name.
    bed_rows = [
        ("7", 117_559_500, 117_559_820, "TGT_009"),
        ("1", 925_900, 926_180, "TGT_003"),
        ("1", 11_000, 11_240, "TGT_001"),
        ("1", 11_200, 11_500, "TGT_001"),  # overlaps the previous one, repeated name
        ("1", 65_419, 65_650, "TGT_002"),
        ("1", 65_650, 65_900, "TGT_002b"),  # book-ended
        ("17", 7_668_500, 7_668_830, "TGT_012"),
        ("17", 7_670_600, 7_670_608, "TGT_013"),  # only 8 bp long
        ("X", 31_100_000, 31_100_300, "TGT_016"),
        ("2", 47_403_000, 47_403_320, "TGT_005"),
    ]
    out[EX / "messy" / "targets.bed"] = "".join(
        f"{c}\t{s}\t{e}\t{n}\r\n" for c, s, e, n in bed_rows
    ).encode()
    sheet = [
        "sample_id,fastq_1,fastq_2,sex,family_id,paternal_id,maternal_id,library_id,lane",
        "S01,S01_R1.fastq.gz,S01_R2.fastq.gz,male,FAM2,S02,S03,LIB1,1",
        "S02,S02_R1.fastq.gz,S02_R2.fastq.gz,male,FAM2,,,LIB2,1",
        "S01,S04_R1.fastq.gz,S04_R2.fastq.gz,female,FAM2,,,LIB3,1",  # duplicate sample_id
        "S 05/b,S05_R1.fastq.gz,S05_R2.fastq.gz,female,FAM3,,,LIB4,1",  # unsafe characters
        "S06,S06_R1.fastq.gz,S06_R2.fastq.gz,banana,FAM3,,,LIB5,1",  # bad sex value
        "S07,S07_R1.fastq.gz,S07_R2.fastq.gz,female,FAM3,S07,S99,LIB6,1",  # own and missing parent
        "S08,S08_R2.fastq.gz,S08_R1.fastq.gz,male,,,,LIB7,1",  # read 1 and read 2 swapped
        "S09,S09_R1.fastq.gz,S09_R2.fastq.gz,female,,,,LIB8,1",  # truncated file
        "S10,S10_R1.fastq.gz,S10_R2.fastq.gz,male,,,,LIB9,1",  # file not delivered
        "S11,S01_R1.fastq.gz,S11_R2.fastq.gz,male,,,,LIB10,1",  # re-uses S01's read 1 file
    ]
    out[EX / "messy" / "samples.csv"] = "\n".join(sheet) + "\n"
    for sid in ("S01", "S02", "S03", "S04", "S05", "S06", "S07", "S11"):
        out[EX / "messy" / "reads" / f"{sid}_R1.fastq.gz"] = fastq_bytes(sid, 1)
        out[EX / "messy" / "reads" / f"{sid}_R2.fastq.gz"] = fastq_bytes(sid, 2)
    out[EX / "messy" / "reads" / "S08_R1.fastq.gz"] = fastq_bytes("S08", 1)
    out[EX / "messy" / "reads" / "S08_R2.fastq.gz"] = fastq_bytes("S08", 2)
    out[EX / "messy" / "reads" / "S09_R1.fastq.gz"] = fastq_bytes("S09", 1, n=400, truncate=True)
    out[EX / "messy" / "reads" / "S09_R2.fastq.gz"] = fastq_bytes("S09", 2, n=400)
    return out


def build_reports() -> dict[Path, bytes | str]:
    os.environ["SOURCE_DATE_EPOCH"] = FIXED_EPOCH
    from ngs_preflight.report.html import render_html
    from ngs_preflight.report.json_report import render_json
    from ngs_preflight.report.markdown import render_markdown
    from ngs_preflight.runner import Options, run_preflight

    out: dict[Path, bytes | str] = {}
    cwd = Path.cwd()
    os.chdir(ROOT)  # so report paths are relative to the repository root
    try:
        for name in ("good", "messy"):
            opts = Options(
                samplesheet=f"examples/{name}/samples.csv",
                beds=[f"examples/{name}/targets.bed"],
                reference="examples/reference/GRCh38_no_alt_analysis_set.fa.fai",
                reads_dir=f"examples/{name}/reads",
            )
            report = run_preflight(opts)
            out[EX / "reports" / f"{name}.html"] = render_html(report)
            out[EX / "reports" / f"{name}.json"] = render_json(report)
            out[EX / "reports" / f"{name}.md"] = render_markdown(report)
    finally:
        os.chdir(cwd)
    return out


def expected_files() -> dict[Path, bytes | str]:
    files: dict[Path, bytes | str] = {}
    files.update(build_good())
    files.update(build_messy())
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="only compare, do not write")
    args = parser.parse_args()
    if not REFERENCE.exists():
        print(f"missing {REFERENCE}", file=sys.stderr)
        return 3
    inputs = expected_files()
    if not args.check:
        for path, data in inputs.items():
            write(path, data)
    reports = build_reports()  # reads the inputs on disk
    stale = []
    for path, data in {**inputs, **reports}.items():
        want = data.encode("utf-8") if isinstance(data, str) else data
        if args.check:
            if not path.exists() or path.read_bytes() != want:
                stale.append(path)
        else:
            write(path, want)
    if args.check:
        for path in stale:
            print(f"out of date: {path.relative_to(ROOT)}", file=sys.stderr)
        return 1 if stale else 0
    print(
        f"Wrote {len(inputs)} input files and {len(reports)} reports under {EX.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
