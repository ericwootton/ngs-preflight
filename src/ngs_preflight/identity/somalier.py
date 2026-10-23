"""Thin wrapper around the ``somalier`` binary (``extract`` and ``relate``).

somalier is not bundled. It is found on PATH, or run through a command prefix given with
``--somalier-cmd`` / ``PREFLIGHT_SOMALIER_CMD`` (for example a ``docker run ... somalier`` line).
Every path handed to somalier must be visible to that command (mount it when using Docker).
"""

from __future__ import annotations

import csv
import shlex
import shutil
import struct
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED_VERSION = "0.3.5"
SOMALIER_SUFFIX = ".somalier"
EXTRACTABLE_SUFFIXES = (".bam", ".cram", ".vcf", ".vcf.gz", ".bcf", ".g.vcf.gz")


class SomalierError(Exception):
    """somalier ran but failed, or produced output we cannot read."""


@dataclass
class SomalierSample:
    sample_id: str
    inferred_sex: str  # "male", "female" or "unknown"
    depth_mean: float | None = None
    n_hom_ref: int = 0
    n_het: int = 0
    n_hom_alt: int = 0
    n_unknown: int = 0
    x_depth_mean: float | None = None
    y_depth_mean: float | None = None
    x_het: int | None = None
    x_n: int | None = None

    @property
    def informative_sites(self) -> int:
        """Sites somalier could genotype confidently in this sample."""
        return self.n_hom_ref + self.n_het + self.n_hom_alt


@dataclass
class SomalierPair:
    sample_a: str
    sample_b: str
    relatedness: float
    ibs0: int = 0
    ibs2: int = 0
    n: int = 0


@dataclass
class IdentityResult:
    samples: dict[str, SomalierSample] = field(default_factory=dict)
    pairs: list[SomalierPair] = field(default_factory=list)

    def pair(self, a: str, b: str) -> SomalierPair | None:
        for p in self.pairs:
            if {p.sample_a, p.sample_b} == {a, b}:
                return p
        return None


def read_somalier_sample_id(path: str | Path) -> str | None:
    """Sample name stored in a ``.somalier`` file (version byte, name length, name)."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(2)
            if len(head) < 2:
                return None
            (_version, name_len) = struct.unpack("<bB", head)
            name = handle.read(name_len)
    except OSError:
        return None
    if len(name) != name_len:
        return None
    try:
        return name.decode("utf-8")
    except UnicodeDecodeError:
        return None


def rewrite_somalier_sample_id(src: str | Path, dst: str | Path, new_id: str) -> None:
    """Copy a ``.somalier`` file under a different sample name (used for test fixtures)."""
    data = Path(src).read_bytes()
    name_len = data[1]
    encoded = new_id.encode("utf-8")
    if len(encoded) > 255:
        raise SomalierError("sample name too long")
    Path(dst).write_bytes(data[:1] + bytes([len(encoded)]) + encoded + data[2 + name_len :])


def _to_float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "", "NA", "nan", "-nan") else None
    except ValueError:
        return None


def _to_int(value: str | None) -> int:
    try:
        return int(float(value)) if value not in (None, "", "NA") else 0
    except ValueError:
        return 0


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header: list[str] | None = None
        rows: list[dict[str, str]] = []
        for rec in reader:
            if not rec:
                continue
            if header is None:
                header = [c.lstrip("#") for c in rec]
                continue
            rows.append(dict(zip(header, rec, strict=False)))
    return rows


_SEX = {"1": "male", "2": "female"}


def parse_samples_tsv(path: Path) -> dict[str, SomalierSample]:
    samples: dict[str, SomalierSample] = {}
    for row in _rows(path):
        sid = row.get("sample_id", "")
        if not sid:
            continue
        samples[sid] = SomalierSample(
            sample_id=sid,
            inferred_sex=_SEX.get(row.get("sex", ""), "unknown"),
            depth_mean=_to_float(row.get("depth_mean")),
            n_hom_ref=_to_int(row.get("n_hom_ref")),
            n_het=_to_int(row.get("n_het")),
            n_hom_alt=_to_int(row.get("n_hom_alt")),
            n_unknown=_to_int(row.get("n_unknown")),
            x_depth_mean=_to_float(row.get("X_depth_mean")),
            y_depth_mean=_to_float(row.get("Y_depth_mean")),
            x_het=_to_int(row.get("X_het")) if "X_het" in row else None,
            x_n=_to_int(row.get("X_n")) if "X_n" in row else None,
        )
    return samples


def parse_pairs_tsv(path: Path) -> list[SomalierPair]:
    pairs = []
    for row in _rows(path):
        rel = _to_float(row.get("relatedness"))
        if rel is None:
            continue
        pairs.append(
            SomalierPair(
                sample_a=row.get("sample_a", ""),
                sample_b=row.get("sample_b", ""),
                relatedness=rel,
                ibs0=_to_int(row.get("ibs0")),
                ibs2=_to_int(row.get("ibs2")),
                n=_to_int(row.get("n")),
            )
        )
    return pairs


class SomalierRunner:
    def __init__(self, cmd: str | None = None) -> None:
        self.cmd_text = cmd or "somalier"
        self.cmd = shlex.split(self.cmd_text, posix=True)

    def available(self) -> tuple[bool, str]:
        """(True, version line) if somalier runs; else (False, plain-language reason)."""
        if not self.cmd:
            return False, "the somalier command is empty"
        if shutil.which(self.cmd[0]) is None:
            return False, f"'{self.cmd[0]}' was not found on this machine"
        try:
            proc = subprocess.run(
                [*self.cmd], capture_output=True, text=True, timeout=120, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"running '{self.cmd_text}' failed ({exc})"
        text = proc.stdout + proc.stderr
        if "somalier version" not in text:
            return False, f"'{self.cmd_text}' did not behave like somalier: {text.strip()[:120]!r}"
        version = next(
            (
                ln.split("version:")[1].strip()
                for ln in text.splitlines()
                if "somalier version" in ln
            ),
            "",
        )
        return True, version

    def _run(self, args: list[str], timeout: int | None = None) -> str:
        try:
            proc = subprocess.run(
                [*self.cmd, *args], capture_output=True, text=True, timeout=timeout, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SomalierError(f"could not run somalier: {exc}") from exc
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout).strip().splitlines()[-5:]
            raise SomalierError(f"somalier {args[0]} failed: " + " | ".join(tail))
        return proc.stdout + proc.stderr

    def extract(self, source: Path, sites: Path, fasta: Path | None, out_dir: Path) -> list[Path]:
        """Run ``somalier extract``; return the ``.somalier`` files it created."""
        out_dir.mkdir(parents=True, exist_ok=True)
        before = set(out_dir.glob("*" + SOMALIER_SUFFIX))
        args = ["extract", "-d", str(out_dir), "-s", str(sites)]
        if fasta is not None:
            args += ["-f", str(fasta)]
        args.append(str(source))
        self._run(args)
        created = sorted(set(out_dir.glob("*" + SOMALIER_SUFFIX)) - before)
        if not created:
            raise SomalierError(f"somalier extract produced no output for {source}")
        return created

    def relate(
        self, files: list[Path], ped: Path | None, sites: Path | None, out_prefix: Path
    ) -> IdentityResult:
        args = ["relate", "-o", str(out_prefix)]
        if ped is not None:
            args += ["--ped", str(ped)]
        if sites is not None:
            args += ["--sites", str(sites)]
        args += [str(f) for f in files]
        self._run(args)
        samples_tsv = Path(str(out_prefix) + ".samples.tsv")
        pairs_tsv = Path(str(out_prefix) + ".pairs.tsv")
        if not samples_tsv.exists() or not pairs_tsv.exists():
            raise SomalierError("somalier relate did not write its .samples.tsv / .pairs.tsv files")
        return IdentityResult(parse_samples_tsv(samples_tsv), parse_pairs_tsv(pairs_tsv))
