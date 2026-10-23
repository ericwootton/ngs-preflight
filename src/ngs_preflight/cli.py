"""Command-line interface: ``preflight check | explain | fix-bed | docs``.

Exit codes for ``check``: 0 pass, 1 errors found, 2 warnings only, 3 tool or usage error.
"""

from __future__ import annotations

import argparse
import difflib
import os
import sys
import textwrap
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from ngs_preflight import __version__
from ngs_preflight.docs_gen import REQUIRES_TEXT, anchor, stale_docs, write_docs
from ngs_preflight.errors import PreflightError
from ngs_preflight.fixbed import FixOptions, write_fixed
from ngs_preflight.reference import load_reference
from ngs_preflight.registry import all_checks, get_check
from ngs_preflight.report.html import render_html
from ngs_preflight.report.json_report import render_json
from ngs_preflight.report.markdown import render_markdown
from ngs_preflight.report.text import render_text
from ngs_preflight.runner import Options, run_preflight

EXIT_PASS, EXIT_ERRORS, EXIT_WARNINGS, EXIT_USAGE = 0, 1, 2, 3
FORMATS = ("text", "json", "markdown", "html")
CATALOGUE_URL = "https://ericwootton.github.io/ngs-preflight/checks/"


class _Parser(argparse.ArgumentParser):
    """argparse exits with 2 on bad usage, but 2 means 'warnings only' here, so use 3."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="preflight",
        description="Check NGS inputs (target BED, sample sheet, reference, sample identity) "
        "before the first run, and explain problems in plain language.",
        epilog="Exit codes for 'check': 0 pass, 1 errors, 2 warnings only, 3 tool or usage error.",
    )
    parser.add_argument("--version", action="version", version=f"ngs-preflight {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)

    c = sub.add_parser("check", help="check a submission and write a report")
    c.add_argument("--samplesheet", metavar="FILE", help="sample sheet (CSV or TSV)")
    c.add_argument(
        "--bed", action="append", default=[], metavar="FILE", help="target BED (repeatable)"
    )
    c.add_argument(
        "--reference", metavar="FILE", help="reference .fai or .dict (or a FASTA with .fai)"
    )
    c.add_argument(
        "--reads-dir", metavar="DIR", help="folder holding the files named in the sample sheet"
    )
    c.add_argument(
        "--expected-build", choices=["GRCh38", "GRCh37"], help="flag a reference of another build"
    )
    c.add_argument(
        "--identity", action="store_true", help="run the optional sample identity checks (somalier)"
    )
    c.add_argument("--sites", metavar="FILE", help="somalier sites VCF (sites.hg38.vcf.gz)")
    c.add_argument(
        "--alignments-or-vcfs",
        nargs="+",
        default=[],
        metavar="FILE",
        help="BAM/CRAM/VCF files, or pre-extracted .somalier files, for the identity checks",
    )
    c.add_argument(
        "--fasta", metavar="FILE", help="reference FASTA, needed by somalier to read BAM/CRAM"
    )
    c.add_argument(
        "--somalier-cmd",
        metavar="CMD",
        help="how to run somalier, e.g. 'somalier' or a 'docker run ... somalier' prefix "
        "(default: $PREFLIGHT_SOMALIER_CMD, else 'somalier' on PATH)",
    )
    c.add_argument(
        "--format", choices=FORMATS, default="text", help="report format (default: text)"
    )
    c.add_argument(
        "--out", metavar="FILE", help="write the report to this file instead of the screen"
    )
    c.add_argument("--strict", action="store_true", help="treat warnings as errors")

    e = sub.add_parser("explain", help="show what a check means and how to fix it")
    e.add_argument("check_id", metavar="ID", help="check ID, for example BED003")

    f = sub.add_parser(
        "fix-bed", help="write a corrected copy of a BED file (never edits in place)"
    )
    f.add_argument("bed", metavar="FILE", help="BED file to fix")
    group = f.add_mutually_exclusive_group()
    group.add_argument(
        "--add-chr", action="store_true", help="add the 'chr' prefix (MT becomes chrM)"
    )
    group.add_argument(
        "--strip-chr", action="store_true", help="remove the 'chr' prefix (chrM becomes MT)"
    )
    f.add_argument(
        "--sort", action="store_true", help="sort intervals (reference order with --reference)"
    )
    f.add_argument(
        "--merge",
        action="store_true",
        help="merge overlapping and touching intervals (implies --sort)",
    )
    f.add_argument(
        "--reference", metavar="FILE", help="reference .fai/.dict that sets the sort order"
    )
    f.add_argument("--out", metavar="FILE", help="output file (default: <name>.fixed.bed)")
    f.add_argument("--force", action="store_true", help="overwrite --out if it already exists")

    d = sub.add_parser("docs", help="regenerate docs/checks.md and docs/report.schema.json")
    d.add_argument(
        "--out-dir", default="docs", metavar="DIR", help="folder to write into (default: docs)"
    )
    d.add_argument(
        "--check", action="store_true", help="do not write; exit 1 if the files are out of date"
    )
    return parser


def _want_color() -> bool:
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def _cmd_check(args: argparse.Namespace) -> int:
    somalier_cmd = args.somalier_cmd or os.environ.get("PREFLIGHT_SOMALIER_CMD")
    opts = Options(
        samplesheet=args.samplesheet,
        beds=args.bed,
        reference=args.reference,
        reads_dir=args.reads_dir,
        identity=args.identity,
        sites=args.sites,
        identity_inputs=args.alignments_or_vcfs,
        fasta=args.fasta,
        somalier_cmd=somalier_cmd,
        expected_build=args.expected_build,
        strict=args.strict,
    )
    report = run_preflight(opts)
    fmt = args.format
    if fmt == "json":
        body = render_json(report)
    elif fmt == "markdown":
        body = render_markdown(report)
    elif fmt == "html":
        body = render_html(report)
    else:
        body = render_text(report, color=_want_color() and not args.out)
    if args.out:
        Path(args.out).write_text(body, encoding="utf-8", newline="\n")
        print(f"{report.headline}. Report written to {args.out}")
    else:
        sys.stdout.write(body)
    return report.exit_code


def wrap(text: str) -> str:
    return textwrap.fill(text, width=88, subsequent_indent="  ")


def _cmd_explain(args: argparse.Namespace) -> int:
    spec = get_check(args.check_id)
    if spec is None:
        ids = [c.id for c in all_checks()]
        close = difflib.get_close_matches(args.check_id.upper(), ids, n=3)
        hint = f" Did you mean {', '.join(close)}?" if close else ""
        raise PreflightError(
            f"unknown check ID {args.check_id!r}.{hint} Known IDs: {', '.join(ids)}"
        )
    lines = [f"{spec.id}: {spec.title}", f"Severity: {spec.severity.value}"]
    needs = [REQUIRES_TEXT[r] for r in spec.requires]
    if spec.id.startswith("ID"):
        needs = ["--identity, somalier and a sites file"]
    if needs:
        lines.append("Needs: " + ", ".join(needs))
    lines += [
        "",
        "What you will see:",
        wrap("  " + spec.message),
        "",
        "How it works:",
        wrap("  " + spec.detail),
        "",
        "How to fix it:",
        wrap("  " + spec.fix),
    ]
    if spec.notes:
        lines += ["", "Notes:", *[wrap("  " + p) for p in spec.notes.split("\n\n")]]
    lines += ["", f"Catalogue: {CATALOGUE_URL}#{anchor(spec.id)}"]
    print("\n".join(lines))
    return EXIT_PASS


def _cmd_fix_bed(args: argparse.Namespace) -> int:
    reference = load_reference(args.reference) if args.reference else None
    opts = FixOptions(
        add_chr=args.add_chr,
        strip_chr=args.strip_chr,
        sort=args.sort,
        merge=args.merge,
        reference=reference,
    )
    dst, summary = write_fixed(args.bed, args.out, opts, force=args.force)
    print("\n".join(summary.lines(args.bed, str(dst))))
    return EXIT_PASS


def _cmd_docs(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    if args.check:
        stale = stale_docs(out_dir)
        if stale:
            print("Out of date: " + ", ".join(str(p) for p in stale), file=sys.stderr)
            print("Run: preflight docs", file=sys.stderr)
            return EXIT_ERRORS
        print("Docs are up to date.")
        return EXIT_PASS
    for path in write_docs(out_dir):
        print(f"Wrote {path}")
    return EXIT_PASS


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        handlers = {
            "check": _cmd_check,
            "explain": _cmd_explain,
            "fix-bed": _cmd_fix_bed,
            "docs": _cmd_docs,
        }
        return handlers[args.command](args)
    except PreflightError as exc:
        print(f"preflight: error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except OSError as exc:
        print(f"preflight: error: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
