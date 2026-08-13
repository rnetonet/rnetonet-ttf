"""Validate the built `rnetonet` family. Acts as the acceptance gate for `build.py`.

Three stages, each of which can fail the run (non-zero exit) so this doubles as a CI gate:

1. OTS (OpenType Sanitizer) must accept every output -- the hard "will browsers and
   rasterizers actually load this" bar.
2. Structural RIBBI checks: one shared family name, correct subfamilies / weight classes /
   style bits, native TrueType hinting intact (fpgm/cvt present -> integer-ppem `head.flags`
   bit set), STAT present, `fvar` gone (fully instanced), smart-dropout present in `prep`,
   uniform advance widths (monospace), Windows-only name records, no DSIG.
3. fontbakery `check-universal` must surface no FAIL beyond the known inherited set
   (EXPECTED_FAILS). Any *new* FAIL fails the run; the expected ones are reported but tolerated.

Cascadia Mono is the ligature-free cut of Cascadia, so there is no coding-ligature stage here
(the family has none by design).

The EXPECTED_FAILS are inherited from the upstream Cascadia design, not regressions introduced
by the rebrand -- verified by diffing against plain-instanced controls, where the rebrand
introduces zero new FAILs and in fact fixes several the raw instance has (smart_dropout,
no_mac_entries):

    arabic_high_hamza              upstream glyph-composition choice in Cascadia
    case_mapping                   upstream: a few cased glyphs lack round-trip case pairs
    family/win_ascent_and_descent  upstream: native win metrics don't cover the full glyph bbox
    nested_components              upstream: composite glyphs reference other composites

Usage:
    python pipeline/validate.py
"""

import json
import os
import re
import subprocess
import sys
import tempfile

import ots
from fontTools.ttLib import TTFont

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAMILY = "rnetonet"
OUT_DIR = os.path.join(REPO, FAMILY)

ITALIC, BOLD, REGULAR, USE_TYPO, WWS = 1 << 0, 1 << 5, 1 << 6, 1 << 7, 1 << 8
SMART_DROPOUT = bytes([0xB8, 0x01, 0xFF, 0x85, 0xB0, 0x04, 0x8D])

# FAILs known to come from the upstream Cascadia design, keyed by fontbakery check id. Anything
# not in here is treated as a regression. See the module docstring for how this set is verified.
EXPECTED_FAILS = {
    "arabic_high_hamza",
    "case_mapping",
    "family/win_ascent_and_descent",
    "nested_components",
}

# filename -> expected structural properties
SPECS = {
    "rnetonet-Regular.ttf": dict(subfamily="Regular", weight=400, bold=False, italic=False),
    "rnetonet-Bold.ttf": dict(subfamily="Bold", weight=700, bold=True, italic=False),
    "rnetonet-RegularItalic.ttf": dict(subfamily="Italic", weight=400, bold=False, italic=True),
    "rnetonet-BoldItalic.ttf": dict(subfamily="Bold Italic", weight=700, bold=True, italic=True),
}


class Report:
    """Collects PASS/FAIL lines and remembers whether anything failed."""

    def __init__(self):
        self.ok = True

    def check(self, condition, label, detail=""):
        mark = "PASS" if condition else "FAIL"
        if not condition:
            self.ok = False
        print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not condition else ""))
        return condition


def stage_ots(report):
    print("\n== OTS sanitize ==")
    for fn in SPECS:
        path = os.path.join(OUT_DIR, fn)
        result = ots.sanitize(path, capture_output=True, text=True)
        detail = (result.stdout or "") + (result.stderr or "")
        report.check(result.returncode == 0, f"{fn} sanitizes", detail.strip())


def stage_structure(report):
    print("\n== Structural / RIBBI ==")
    families = set()
    for fn, spec in SPECS.items():
        path = os.path.join(OUT_DIR, fn)
        font = TTFont(path, lazy=True)
        name, os2, head = font["name"], font["OS/2"], font["head"]

        fam = name.getDebugName(1)
        families.add(fam)
        report.check(fam == FAMILY, f"{fn}: nameID1 == '{FAMILY}'", f"got {fam!r}")
        report.check(name.getDebugName(2) == spec["subfamily"],
                     f"{fn}: nameID2 == '{spec['subfamily']}'", f"got {name.getDebugName(2)!r}")
        ps = name.getDebugName(6) or ""
        report.check(ps.startswith(f"{FAMILY}-") and " " not in ps,
                     f"{fn}: PostScript name well-formed", f"got {ps!r}")

        report.check(os2.usWeightClass == spec["weight"],
                     f"{fn}: usWeightClass == {spec['weight']}", f"got {os2.usWeightClass}")

        sel = os2.fsSelection
        report.check(bool(sel & BOLD) == spec["bold"], f"{fn}: fsSelection BOLD == {spec['bold']}")
        report.check(bool(sel & ITALIC) == spec["italic"], f"{fn}: fsSelection ITALIC == {spec['italic']}")
        report.check(bool(sel & REGULAR) == (not spec["bold"] and not spec["italic"]),
                     f"{fn}: fsSelection REGULAR correct")
        report.check(bool(sel & USE_TYPO), f"{fn}: fsSelection USE_TYPO_METRICS set")
        report.check(bool(sel & WWS), f"{fn}: fsSelection WWS set")

        mac = head.macStyle
        report.check(bool(mac & 0b01) == spec["bold"], f"{fn}: macStyle bold bit == {spec['bold']}")
        report.check(bool(mac & 0b10) == spec["italic"], f"{fn}: macStyle italic bit == {spec['italic']}")

        # Cascadia is manually hinted (fpgm/cvt), so head.flags bit 3 must be set for PPEM to
        # round to integers -- otherwise the instructions misfire at fractional sizes.
        if "fpgm" in font or "cvt " in font:
            report.check(bool(head.flags & (1 << 3)), f"{fn}: head.flags integer-ppem bit set (hinted)")

        report.check("fvar" not in font, f"{fn}: fully instanced (no fvar)")
        report.check("STAT" in font, f"{fn}: STAT present")
        report.check("DSIG" not in font, f"{fn}: no DSIG")

        prep = font["prep"].program.getBytecode() if "prep" in font else b""
        report.check(SMART_DROPOUT in prep, f"{fn}: smart-dropout instruction in prep")

        widths = {w for w, _ in font["hmtx"].metrics.values() if w > 0}
        report.check(len(widths) == 1, f"{fn}: monospace (uniform advance width)", f"widths={sorted(widths)}")

        non_windows = [r for r in name.names if r.platformID != 3]
        report.check(not non_windows, f"{fn}: name records Windows-only",
                     f"{len(non_windows)} non-Windows records")

    report.check(families == {FAMILY}, f"single shared family name across all four",
                 f"got {families}")
    report.check({SPECS[f]["subfamily"] for f in SPECS} == {"Regular", "Bold", "Italic", "Bold Italic"},
                 "RIBBI subfamilies complete")


def _check_id(check):
    match = re.search(r"<FontBakeryCheck:([^>]+)>", check["key"][1])
    return match.group(1) if match else check["key"][1]


def stage_fontbakery(report):
    print("\n== fontbakery check-universal (FAIL level) ==")
    fonts = [os.path.join(OUT_DIR, fn) for fn in SPECS]
    with tempfile.TemporaryDirectory() as tmp:
        json_path = os.path.join(tmp, "fb.json")
        subprocess.run(
            [sys.executable, "-m", "fontbakery", "check-universal",
             "--loglevel", "FAIL", "--no-progress", "-C", "--json", json_path, *fonts],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        data = json.load(open(json_path, encoding="utf-8"))

    unexpected = {}
    expected_seen = {}
    for section in data["sections"]:
        for check in section["checks"]:
            if check["result"] != "FAIL":
                continue
            cid = _check_id(check)
            fn = (check.get("filename") or "<family>").split("\\")[-1].split("/")[-1]
            bucket = expected_seen if cid in EXPECTED_FAILS else unexpected
            bucket.setdefault(cid, []).append(fn)

    counts = data["result"]
    print(f"  totals: PASS={counts.get('PASS')} FAIL={counts.get('FAIL')} "
          f"WARN={counts.get('WARN')} SKIP={counts.get('SKIP')} INFO={counts.get('INFO')}")
    for cid in sorted(expected_seen):
        print(f"  [expected FAIL] {cid} ({len(expected_seen[cid])} files)")
    for cid in sorted(unexpected):
        print(f"  [UNEXPECTED FAIL] {cid}: {', '.join(unexpected[cid])}")

    report.check(not unexpected, "no fontbakery FAIL beyond the expected/inherited set")


def main():
    missing = [fn for fn in SPECS if not os.path.exists(os.path.join(OUT_DIR, fn))]
    if missing:
        print(f"Outputs missing: {missing}\nRun `python pipeline/build.py` first.")
        return 1

    report = Report()
    stage_ots(report)
    stage_structure(report)
    stage_fontbakery(report)

    print("\n" + ("ALL CHECKS PASSED" if report.ok else "VALIDATION FAILED"))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
