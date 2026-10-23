"""Fast gzip / BGZF integrity checks (SS007).

Strategy, chosen so that the check stays fast on multi-gigabyte files:

* every file: gzip magic bytes, a clean header, and the first few MiB decompress;
* BGZF files (``.bam``, bgzipped FASTQ): the 28-byte end-of-file marker is present,
  which is what a truncated download or an interrupted copy loses;
* other gzip files up to ``FULL_VERIFY_LIMIT`` bytes: the whole stream is decompressed
  and its CRC is verified;
* larger non-BGZF gzip files cannot be proven complete cheaply; the tail is checked for
  a plausible trailer only, and the result says so.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from ngs_preflight.bam import BGZF_EOF, has_bgzf_eof

FULL_VERIFY_LIMIT = 32 * 1024 * 1024
HEAD_BYTES = 4 * 1024 * 1024
_CHUNK = 1 << 20
GZIP_MAGIC = bytes([0x1F, 0x8B])


@dataclass(frozen=True)
class GzipResult:
    ok: bool
    problem: str = ""
    verified_fully: bool = False


def _is_bgzf(head: bytes) -> bool:
    return len(head) >= 18 and head[3] & 4 == 4 and head[12:14] == b"BC"


def _inflate_prefix(path: Path, limit: int | None) -> tuple[bool, str]:
    """Inflate up to ``limit`` compressed bytes (all if None). Returns (ok, problem)."""
    decomp = zlib.decompressobj(wbits=31)
    in_member = False
    consumed = 0
    try:
        with path.open("rb") as handle:
            while limit is None or consumed < limit:
                chunk = handle.read(_CHUNK)
                if not chunk:
                    break
                consumed += len(chunk)
                data = chunk
                while data:
                    in_member = True
                    decomp.decompress(data)
                    if decomp.eof:
                        data = decomp.unused_data
                        decomp = zlib.decompressobj(wbits=31)
                        in_member = False
                        if data and data[:2] != GZIP_MAGIC:
                            return False, "unexpected bytes after the end of a compressed block"
                    else:
                        data = b""
    except (zlib.error, OSError) as exc:
        return False, f"decompression failed: {exc}"
    if limit is None and in_member:
        return False, "the compressed data ends unexpectedly (the file looks truncated)"
    return True, ""


def check_gzip(path: str | Path) -> GzipResult:
    p = Path(path)
    try:
        size = p.stat().st_size
        with p.open("rb") as handle:
            head = handle.read(64)
    except OSError as exc:
        return GzipResult(False, f"cannot read the file: {exc}")
    if size == 0:
        return GzipResult(False, "the file is empty")
    if head[:2] != b"\x1f\x8b":
        return GzipResult(False, "the file is not gzip-compressed (missing gzip signature)")
    if _is_bgzf(head):
        if not has_bgzf_eof(p):
            return GzipResult(
                False, "the end-of-file marker is missing (the file looks truncated or incomplete)"
            )
        ok, problem = _inflate_prefix(p, HEAD_BYTES)
        return GzipResult(ok, problem, verified_fully=False)
    if size <= FULL_VERIFY_LIMIT:
        ok, problem = _inflate_prefix(p, None)
        return GzipResult(ok, problem, verified_fully=ok)
    ok, problem = _inflate_prefix(p, HEAD_BYTES)
    if not ok:
        return GzipResult(False, problem)
    with p.open("rb") as handle:
        handle.seek(-8, 2)
        _crc, isize = struct.unpack("<II", handle.read(8))
    if isize == 0:
        return GzipResult(False, "the gzip trailer reports zero bytes of content")
    return GzipResult(True, "", verified_fully=False)


__all__ = ["BGZF_EOF", "GzipResult", "check_gzip"]
