"""Sample-sheet checks (SS001-SS009)."""

from __future__ import annotations

import re
import zlib
from collections.abc import Iterator
from pathlib import Path

from ngs_preflight.context import SheetContext
from ngs_preflight.fastq import mate_marker, read_names
from ngs_preflight.gzcheck import check_gzip
from ngs_preflight.models import Severity
from ngs_preflight.registry import Hit, check
from ngs_preflight.samplesheet import SampleRow, near_miss
from ngs_preflight.util import cap, plural, quote_list, verb

_URL = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_FASTQ_EXT = re.compile(r"(?i)\.f(ast)?q(\.gz)?$")
_READ_FILES = ("fastq_1", "fastq_2")


def _is_url(value: str) -> bool:
    return bool(_URL.match(value))


def _read_paths(row: SampleRow) -> Iterator[str]:
    for col in _READ_FILES:
        value = getattr(row, col)
        if value:
            yield value


@check(
    id="SS001",
    severity=Severity.ERROR,
    title="Required columns are present and filled in",
    message="{problem} The workflow cannot tell which samples and files to process without them.",
    detail=(
        "The schema lives in src/ngs_preflight/schema/samplesheet.yaml. Required columns: "
        "sample_id, fastq_1, fastq_2. Optional: sex, family_id, paternal_id, maternal_id, "
        "library_id, lane. Column names must match exactly (case-sensitive); a close match such "
        "as 'Sample ID' is reported as a hint. Blank cells in required columns are also reported."
    ),
    fix="{fix}",
    scope="samplesheet",
)
def ss001(ctx: SheetContext) -> Iterator[Hit]:
    sheet = ctx.sheet
    if sheet.empty or not sheet.header:
        yield Hit(
            {
                "problem": "The sample sheet is empty.",
                "fix": "Add a header row (sample_id, fastq_1, fastq_2) and one row per sample.",
            }
        )
        return
    missing = [c for c in ctx.schema.required if c not in sheet.header]
    if missing:
        hints = []
        for col in missing:
            alt = near_miss(sheet.header, col)
            if alt:
                hints.append(f'"{alt}" should be spelled "{col}"')
        hint = " (" + "; ".join(hints) + ")" if hints else ""
        yield Hit(
            {
                "problem": (
                    f"{cap(plural(len(missing), 'required column'))} missing from the sample "
                    f"sheet: {quote_list(missing)}{hint}."
                ),
                "fix": (
                    "Add the missing columns, or rename them to the exact spelling above. "
                    "Required columns are: " + ", ".join(ctx.schema.required) + "."
                ),
            },
            technical="Columns found: " + ", ".join(sheet.header),
        )
    blanks: dict[str, list[int]] = {}
    for col in ctx.schema.required:
        if col in sheet.header:
            lines = [r.line for r in sheet.rows if not getattr(r, col, "")]
            if lines:
                blanks[col] = lines
    if blanks:
        total = sum(len(v) for v in blanks.values())
        first_col, first_lines = next(iter(blanks.items()))
        yield Hit(
            {
                "problem": (
                    f"{cap(plural(total, 'required cell'))} in the sample sheet "
                    f"{'is' if total == 1 else 'are'} empty (for example column "
                    f'"{first_col}" on line {first_lines[0]}).'
                ),
                "fix": "Fill in every required cell, or delete rows you do not need.",
            },
            technical="; ".join(
                f"{c}: lines {', '.join(map(str, v[:8]))}" for c, v in blanks.items()
            ),
        )


@check(
    id="SS002",
    severity=Severity.ERROR,
    title="Sample IDs are unique",
    message=(
        '{count} on more than one row without a different lane number (for example "{sample}" '
        "on lines {lines}). Two different samples with the same ID cannot be told apart, and their "
        "results would be merged or overwritten."
    ),
    detail=(
        "Rows may repeat a sample_id only when a 'lane' column exists and each repeated row has a "
        "distinct, non-blank lane (one sample sequenced on several lanes). Anything else is a "
        "duplicate."
    ),
    fix=(
        "Give every sample a unique ID. If one sample was sequenced on several lanes, add a lane "
        "column and give each row its own lane number."
    ),
    scope="samplesheet",
)
def ss002(ctx: SheetContext) -> Iterator[Hit]:
    groups: dict[str, list[SampleRow]] = {}
    for row in ctx.sheet.rows:
        if row.sample_id:
            groups.setdefault(row.sample_id, []).append(row)
    has_lane = ctx.sheet.has_column("lane")
    dup: dict[str, list[int]] = {}
    for sid, rows in groups.items():
        if len(rows) < 2:
            continue
        lanes = [r.lane for r in rows]
        if not has_lane or any(not ln for ln in lanes) or len(set(lanes)) != len(lanes):
            dup[sid] = [r.line for r in rows]
    if dup:
        sample, lines = next(iter(dup.items()))
        yield Hit(
            {
                "count": cap(plural(len(dup), "sample ID")) + verb(len(dup), " appears", " appear"),
                "sample": sample,
                "lines": ", ".join(map(str, lines)),
            },
            technical="Duplicated: "
            + "; ".join(f"{k} (lines {', '.join(map(str, v))})" for k, v in list(dup.items())[:10]),
        )


@check(
    id="SS003",
    severity=Severity.ERROR,
    title="Sample IDs use safe characters",
    message=(
        '{count} not allowed (for example "{example}"). Sample IDs may only use letters, digits, '
        "underscore and hyphen, up to {max_length} characters. Spaces, slashes and other symbols "
        "break file names and many workflow tools."
    ),
    detail=(
        "Pattern from the schema: ^[A-Za-z0-9_-]+$, maximum length 64. Blank IDs are reported by "
        "SS001, not here."
    ),
    fix="Rename the samples using only A-Z, a-z, 0-9, underscore (_) and hyphen (-).",
    scope="samplesheet",
)
def ss003(ctx: SheetContext) -> Iterator[Hit]:
    rule = ctx.schema.sample_id
    pattern = re.compile(rule.pattern)
    bad = [
        r
        for r in ctx.sheet.rows
        if r.sample_id and (not pattern.match(r.sample_id) or len(r.sample_id) > rule.max_length)
    ]
    if bad:
        yield Hit(
            {
                "count": cap(plural(len(bad), "sample ID")) + verb(len(bad), " is", " are"),
                "max_length": rule.max_length,
                "example": bad[0].sample_id,
            },
            technical="Lines: " + ", ".join(str(r.line) for r in bad[:10]),
        )


@check(
    id="SS004",
    severity=Severity.ERROR,
    title="Read files exist and are readable",
    message=(
        '{count} listed in the sample sheet could not be found or opened (for example "{path}" '
        'for sample "{sample}"{why}). The run would fail as soon as it tries to read them.'
    ),
    detail=(
        "Relative paths are resolved against --reads-dir; absolute paths are used as written. "
        "Paths that are URLs (s3://, gs://, https://, ...) cannot be checked and are skipped. A "
        "file of 0 bytes counts as unreadable."
    ),
    fix=(
        "Check the file names for typos and that the files were copied to the folder given with "
        "--reads-dir. Upload any files that are missing."
    ),
    scope="samplesheet",
    requires=("reads_dir",),
)
def ss004(ctx: SheetContext) -> Iterator[Hit]:
    problems: list[tuple[str, str, str]] = []
    skipped_urls = 0
    for row in ctx.sheet.rows:
        for value in _read_paths(row):
            if _is_url(value):
                skipped_urls += 1
                continue
            p = ctx.resolve(value)
            try:
                if not p.is_file():
                    problems.append((value, row.sample_id, "not found"))
                elif p.stat().st_size == 0:
                    problems.append((value, row.sample_id, "the file is empty"))
                else:
                    with p.open("rb") as handle:
                        handle.read(1)
            except OSError:
                problems.append((value, row.sample_id, "cannot be opened"))
    if problems:
        value, sample, why = problems[0]
        yield Hit(
            {
                "count": cap(plural(len(problems), "file")),
                "path": value,
                "sample": sample,
                "why": "" if why == "not found" else f": {why}",
            },
            technical=(
                f"Looked in: {ctx.reads_dir.as_posix() if ctx.reads_dir else ''}. "
                + "; ".join(f"{v} ({s}): {w}" for v, s, w in problems[:10])
                + (f". {skipped_urls} URL path(s) not checked." if skipped_urls else "")
            ),
        )


@check(
    id="SS005",
    severity=Severity.ERROR,
    title="No file is listed twice",
    message=(
        '{count} listed more than once (for example "{path}", used by {users}). Reads from one '
        "file would be counted under several samples, or the same reads used as both read 1 and "
        "read 2."
    ),
    detail=(
        "Paths are compared as written (after normalising slashes). A file appearing in two "
        "rows, or as both fastq_1 and fastq_2 of one row, is reported."
    ),
    fix=(
        "Check that each sample points at its own files. If you copied a row to make a new one, "
        "update its file names."
    ),
    scope="samplesheet",
)
def ss005(ctx: SheetContext) -> Iterator[Hit]:
    users: dict[str, list[str]] = {}
    for row in ctx.sheet.rows:
        for value in _read_paths(row):
            key = value.replace("\\", "/")
            users.setdefault(key, []).append(f"{row.sample_id or '?'} (line {row.line})")
    dup = {k: v for k, v in users.items() if len(v) > 1}
    if dup:
        path, who = next(iter(dup.items()))
        yield Hit(
            {
                "count": cap(plural(len(dup), "file")) + (" is" if len(dup) == 1 else " are"),
                "path": path,
                "users": " and ".join(who[:3]),
            },
            technical="; ".join(f"{k}: {', '.join(v)}" for k, v in list(dup.items())[:10]),
        )


def _pair_problem(ctx: SheetContext, row: SampleRow) -> str | None:
    if not (row.fastq_1 and row.fastq_2):
        return None
    m1, m2 = mate_marker(row.fastq_1), mate_marker(row.fastq_2)
    if m1 and m2:
        if m1[0] != m2[0]:
            return "the two file names differ by more than R1/R2"
        if m1[1] == "2" and m2[1] == "1":
            return "fastq_1 looks like read 2 and fastq_2 like read 1 (swapped)"
        if m1[1] == m2[1]:
            return f"both file names look like read {m1[1]}"
    if _is_url(row.fastq_1) or _is_url(row.fastq_2):
        return None
    if not (_FASTQ_EXT.search(row.fastq_1) and _FASTQ_EXT.search(row.fastq_2)):
        return None
    p1, p2 = ctx.resolve(row.fastq_1), ctx.resolve(row.fastq_2)
    if not (p1.is_file() and p2.is_file()):
        return None
    try:
        n1 = read_names(p1, ctx.pair_sample_size)
        n2 = read_names(p2, ctx.pair_sample_size)
    except (OSError, EOFError, zlib.error, UnicodeError):
        return None  # unreadable files are SS004/SS007's business
    if not n1 or not n2:
        return None
    for i, (a, b) in enumerate(zip(n1, n2, strict=False), 1):
        if a != b:
            return f"read {i} has a different name in each file ({a!r} vs {b!r})"
    if len(n1) != len(n2):
        return f"the files hold different numbers of reads at the start ({len(n1)} vs {len(n2)})"
    return None


@check(
    id="SS006",
    severity=Severity.WARN,
    title="Read 1 and read 2 files pair up",
    message=(
        '{count} not look like matching read 1 / read 2 pairs (for example sample "{sample}": '
        "{why}). Mispaired files make alignment fail or produce nonsense, often only after "
        "hours of compute."
    ),
    detail=(
        "File names are compared after replacing R1/R2 (or _1/_2) with a placeholder. When both "
        "files can be read (--reads-dir), the first 100 read names are compared (the first token "
        "of each header, ignoring a trailing /1 or /2). Files without an R1/R2 marker pass the "
        "name test."
    ),
    fix=(
        "Check that fastq_1 holds the read 1 file and fastq_2 the read 2 file from the same "
        "sequencing run, and that neither was renamed or swapped."
    ),
    scope="samplesheet",
)
def ss006(ctx: SheetContext) -> Iterator[Hit]:
    problems: list[tuple[SampleRow, str]] = []
    for row in ctx.sheet.rows:
        why = _pair_problem(ctx, row)
        if why:
            problems.append((row, why))
    if problems:
        row, why = problems[0]
        yield Hit(
            {
                "count": cap(plural(len(problems), "row"))
                + (" does" if len(problems) == 1 else " do"),
                "sample": row.sample_id,
                "why": why,
            },
            technical="; ".join(f"line {r.line} {r.sample_id}: {w}" for r, w in problems[:10]),
        )


@check(
    id="SS007",
    severity=Severity.WARN,
    title="Compressed files are intact",
    message=(
        '{count} damaged or incomplete (for example "{path}": {why}). A truncated '
        "download or interrupted copy is the usual cause, and it makes runs fail partway through."
    ),
    detail=(
        "Fast check, not a full validation. Every .gz/.bam: gzip signature, clean header, first "
        "4 MiB decompresses. BGZF files (.bam, bgzip FASTQ): the 28-byte end-of-file marker must "
        "be present. Other gzip files up to 32 MiB: the whole stream is decompressed and its CRC "
        "verified. Larger non-BGZF gzip files cannot be proven complete cheaply, so only the head "
        "and trailer are checked."
    ),
    fix=(
        "Copy or download the file again, and compare its checksum (for example md5sum) with the "
        "one given by the sender."
    ),
    scope="samplesheet",
    requires=("reads_dir",),
)
def ss007(ctx: SheetContext) -> Iterator[Hit]:
    seen: set[Path] = set()
    bad: list[tuple[str, str]] = []
    checked = 0
    for row in ctx.sheet.rows:
        for value in _read_paths(row):
            if _is_url(value) or not value.lower().endswith((".gz", ".bgz", ".bam")):
                continue
            p = ctx.resolve(value)
            if p in seen or not p.is_file():
                continue
            seen.add(p)
            checked += 1
            result = check_gzip(p)
            if not result.ok:
                bad.append((value, result.problem))
    if bad:
        yield Hit(
            {
                "count": cap(plural(len(bad), "file"))
                + (" appears" if len(bad) == 1 else " appear"),
                "path": bad[0][0],
                "why": bad[0][1],
            },
            technical=f"{checked} file(s) checked. " + "; ".join(f"{p}: {w}" for p, w in bad[:10]),
        )


@check(
    id="SS008",
    severity=Severity.ERROR,
    title="Sex values are from the allowed list",
    message=(
        '{count} not in the accepted list (for example "{value}" for sample "{sample}"). '
        "Downstream steps and the sex check need a recognised value."
    ),
    detail=(
        "Accepted values (case-insensitive): male/m/1, female/f/2, unknown/u/0/NA/n/a/'.'. A blank "
        "cell is allowed (sex unknown). The vocabulary is defined in "
        "src/ngs_preflight/schema/samplesheet.yaml."
    ),
    fix="Use one of: male, female, unknown (or M, F, U; or 1, 2, 0), or leave the cell blank.",
    scope="samplesheet",
)
def ss008(ctx: SheetContext) -> Iterator[Hit]:
    bad = [r for r in ctx.sheet.rows if r.sex and ctx.schema.sex.classify(r.sex) is None]
    if bad:
        yield Hit(
            {
                "count": cap(plural(len(bad), "value")) + (" is" if len(bad) == 1 else " are"),
                "value": bad[0].sex,
                "sample": bad[0].sample_id,
            },
            technical="Lines: " + ", ".join(str(r.line) for r in bad[:10]),
        )


@check(
    id="SS009",
    severity=Severity.ERROR,
    title="Family relationships are consistent",
    message=(
        "{problem} The family structure is used for relatedness checks and by family-aware "
        "analysis, so an inconsistent one can give wrong results."
    ),
    detail=(
        "Every non-empty paternal_id / maternal_id must be the sample_id of another row, and no "
        "sample may be its own father or mother. Blank, 0, '.', NA, n/a and none mean 'no "
        "parent recorded'."
    ),
    fix=(
        "Add a row for each parent (or clear the parent cell if the parent is not part of this "
        "submission), and make sure nobody is listed as their own parent."
    ),
    scope="samplesheet",
)
def ss009(ctx: SheetContext) -> Iterator[Hit]:
    none_markers = {m.lower() for m in ctx.schema.no_parent_markers}
    ids = {r.sample_id for r in ctx.sheet.rows if r.sample_id}
    missing: list[tuple[SampleRow, str, str]] = []
    own: list[tuple[SampleRow, str]] = []
    for row in ctx.sheet.rows:
        for role, value in (("father", row.paternal_id), ("mother", row.maternal_id)):
            if value.lower() in none_markers:
                continue
            if value == row.sample_id:
                own.append((row, role))
            elif value not in ids:
                missing.append((row, role, value))
    if own:
        row, role = own[0]
        yield Hit(
            {
                "problem": (
                    f"{cap(plural(len(own), 'sample'))} {'is' if len(own) == 1 else 'are'} listed "
                    f"as {'its' if len(own) == 1 else 'their'} own parent "
                    f'(for example "{row.sample_id}" as its own {role}, line {row.line}).'
                )
            },
            technical="Lines: " + ", ".join(str(r.line) for r, _ in own[:10]),
        )
    if missing:
        row, role, value = missing[0]
        yield Hit(
            {
                "problem": (
                    f"{cap(plural(len(missing), 'parent reference'))} point"
                    f"{'s' if len(missing) == 1 else ''} to a sample that is not in the sheet "
                    f'(for example "{row.sample_id}" names "{value}" as its {role}, '
                    f"line {row.line})."
                )
            },
            technical="; ".join(
                f"line {r.line}: {r.sample_id} -> {v} ({ro})" for r, ro, v in missing[:10]
            ),
        )
