"""Test helpers: tiny BAM writer, fake somalier, report shortcuts."""

from __future__ import annotations

import struct
import sys
import textwrap
import zlib
from pathlib import Path

from ngs_preflight.bam import BGZF_EOF
from ngs_preflight.models import Report
from ngs_preflight.runner import Options, run_preflight


def bgzf_block(data: bytes) -> bytes:
    comp = zlib.compressobj(6, zlib.DEFLATED, -15)
    body = comp.compress(data) + comp.flush()
    block_size = len(body) + 25  # header 18 + body + footer 8, minus 1
    header = bytes.fromhex("1f8b08040000000000ff060042430200") + struct.pack("<H", block_size)
    footer = struct.pack("<II", zlib.crc32(data) & 0xFFFFFFFF, len(data))
    return header + body + footer


def make_bam(
    path: Path,
    refs: dict[str, int],
    samples: tuple[str, ...] = ("S1",),
    eof: bool = True,
) -> Path:
    text = "@HD\tVN:1.6\tSO:coordinate\n"
    text += "".join(f"@SQ\tSN:{n}\tLN:{ln}\n" for n, ln in refs.items())
    text += "".join(f"@RG\tID:rg{i}\tSM:{s}\n" for i, s in enumerate(samples))
    raw = b"BAM\x01" + struct.pack("<i", len(text)) + text.encode() + struct.pack("<i", len(refs))
    for name, length in refs.items():
        enc = name.encode() + b"\x00"
        raw += struct.pack("<i", len(enc)) + enc + struct.pack("<i", length)
    data = bgzf_block(raw)
    if eof:
        data += BGZF_EOF
    path.write_bytes(data)
    return path


def check(**kwargs: object) -> Report:
    return run_preflight(Options(**kwargs))  # type: ignore[arg-type]


def ids(report: Report, include_info: bool = False) -> set[str]:
    return {f.check_id for f in report.all_findings() if include_info or f.severity.value != "INFO"}


FAKE_SOMALIER = textwrap.dedent(
    '''
    """A stand-in for the somalier binary, driven by a JSON file next to it."""
    import json, sys
    from pathlib import Path

    here = Path(__file__).parent
    cfg = json.loads((here / "fake_somalier.json").read_text())
    args = sys.argv[1:]
    if not args:
        print("somalier version: 0.3.5")
        sys.exit(0)
    cmd = args[0]
    if cmd == "extract":
        out_dir = Path(args[args.index("-d") + 1])
        src = Path(args[-1])
        if cfg.get("extract_fail"):
            print("boom: cannot open file", file=sys.stderr)
            sys.exit(1)
        name = cfg["extract_names"].get(src.name, src.stem)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / (name + ".somalier")).write_bytes(bytes([4, len(name)]) + name.encode() + b"\\0" * 8)
    elif cmd == "relate":
        prefix = args[args.index("-o") + 1]
        if cfg.get("relate_fail"):
            print("relate exploded", file=sys.stderr)
            sys.exit(2)
        if cfg.get("relate_no_output"):
            sys.exit(0)
        Path(prefix + ".samples.tsv").write_text(cfg["samples_tsv"])
        Path(prefix + ".pairs.tsv").write_text(cfg["pairs_tsv"])
    '''
)


def install_fake_somalier(directory: Path, config: dict[str, object]) -> str:
    """Write the fake somalier and its config; return the --somalier-cmd string."""
    import json

    (directory / "fake_somalier.py").write_text(FAKE_SOMALIER)
    (directory / "fake_somalier.json").write_text(json.dumps(config))
    return f'"{sys.executable}" "{directory / "fake_somalier.py"}"'


SAMPLES_HEADER = (
    "#family_id\tsample_id\tpaternal_id\tmaternal_id\tsex\tphenotype\toriginal_pedigree_sex\t"
    "gt_depth_mean\tgt_depth_sd\tdepth_mean\tdepth_sd\tab_mean\tab_std\tn_hom_ref\tn_het\t"
    "n_hom_alt\tn_unknown\tp_middling_ab\tX_depth_mean\tX_n\tX_hom_ref\tX_het\tX_hom_alt\t"
    "Y_depth_mean\tY_n\n"
)
PAIRS_HEADER = (
    "#sample_a\tsample_b\trelatedness\tibs0\tibs2\thom_concordance\thets_a\thets_b\thets_ab\t"
    "shared_hets\thom_alts_a\thom_alts_b\tshared_hom_alts\tn\tx_ibs0\tx_ibs2\n"
)


def samples_row(
    sid: str,
    sex: str = "1",
    hom_ref: int = 9000,
    het: int = 5000,
    hom_alt: int = 2500,
    unknown: int = 200,
) -> str:
    return (
        f"{sid}\t{sid}\t-9\t-9\t{sex}\t-9\t-9\t30\t5\t30\t5\t0.5\t0.1\t{hom_ref}\t{het}\t{hom_alt}\t"
        f"{unknown}\t0.0\t15\t300\t0\t100\t0\t0\t0\t0\n"
    )


def pairs_row(a: str, b: str, rel: float) -> str:
    return f"{a}\t{b}\t{rel}\t10\t16000\t0.9\t5000\t5000\t3000\t2000\t2500\t2500\t2000\t16500\t1\t300\n"
