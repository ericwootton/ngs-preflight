"""Fail unless the line coverage of one package in a coverage.xml report meets a minimum.

Usage: python scripts/check_coverage.py coverage.xml ngs_preflight/checks 90
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET


def main(argv: list[str]) -> int:
    xml_path, prefix, minimum = argv[1], argv[2].replace("\\", "/"), float(argv[3])
    tree = ET.parse(xml_path)
    hit = total = 0
    for cls in tree.iter("class"):
        filename = cls.get("filename", "").replace("\\", "/")
        if prefix not in filename:
            continue
        for line in cls.iter("line"):
            total += 1
            hit += int(line.get("hits", "0")) > 0
    if total == 0:
        print(f"no lines found under {prefix}")
        return 1
    percent = 100.0 * hit / total
    print(f"{prefix}: {percent:.1f}% line coverage ({hit}/{total}); minimum {minimum:.0f}%")
    return 0 if percent >= minimum else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
