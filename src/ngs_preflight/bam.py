"""Pure-Python reading of BAM headers and BGZF integrity (no pysam / htslib needed)."""

from __future__ import annotations

import gzip
import re
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

# The 28-byte empty BGZF block that must end every BGZF file (SAM spec section 4.1.2).
BGZF_EOF = bytes.fromhex("1f8b08040000000000ff0600424302001b0003000000000000000000")

_SM = re.compile(r"\tSM:([^\t]+)")


class BamError(Exception):
    """The file is not a readable BAM."""


@dataclass
class BamHeader:
    text: str
    references: dict[str, int]  # ordered
    samples: list[str] = field(default_factory=list)


def has_bgzf_eof(path: str | Path) -> bool:
    """True if the file ends with the standard BGZF end-of-file marker."""
    p = Path(path)
    size = p.stat().st_size
    if size < len(BGZF_EOF):
        return False
    with p.open("rb") as handle:
        handle.seek(size - len(BGZF_EOF))
        return handle.read() == BGZF_EOF


def _read_exact(handle: gzip.GzipFile, n: int) -> bytes:
    data = handle.read(n)
    if len(data) != n:
        raise BamError("file ends in the middle of the header")
    return data


def read_bam_header(path: str | Path) -> BamHeader:
    """Read the header text and the reference list from a BAM file."""
    try:
        with gzip.open(path, "rb") as handle:
            if _read_exact(handle, 4) != b"BAM\x01":
                raise BamError("this does not look like a BAM file (missing BAM magic number)")
            (l_text,) = struct.unpack("<i", _read_exact(handle, 4))
            if l_text < 0 or l_text > 256 * 1024 * 1024:
                raise BamError("header text length is not plausible")
            text = _read_exact(handle, l_text).split(b"\x00", 1)[0].decode("utf-8", "replace")
            (n_ref,) = struct.unpack("<i", _read_exact(handle, 4))
            if n_ref < 0 or n_ref > 10_000_000:
                raise BamError("reference count is not plausible")
            refs: dict[str, int] = {}
            for _ in range(n_ref):
                (l_name,) = struct.unpack("<i", _read_exact(handle, 4))
                if l_name < 1 or l_name > 4096:
                    raise BamError("reference name length is not plausible")
                name = _read_exact(handle, l_name).rstrip(b"\x00").decode("utf-8", "replace")
                (l_ref,) = struct.unpack("<i", _read_exact(handle, 4))
                refs[name] = l_ref
    except (OSError, EOFError, zlib.error) as exc:
        raise BamError(f"cannot decompress the file: {exc}") from exc
    samples: list[str] = []
    for line in text.splitlines():
        if line.startswith("@RG"):
            m = _SM.search(line)
            if m and m.group(1) not in samples:
                samples.append(m.group(1))
    return BamHeader(text=text, references=refs, samples=samples)
