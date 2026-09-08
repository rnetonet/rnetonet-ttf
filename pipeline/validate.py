"""Validate the built `rnetonet` family. Acts as the acceptance gate for `build.py`.

Four stages, each of which can fail the run (non-zero exit) so this doubles as a CI gate:

1. OTS (OpenType Sanitizer) must accept every output -- the hard "will browsers and rasterizers
   actually load this" bar.
2. Build scope: `build.py` re-hints and rebrands, and nothing else. `glyf` legitimately changes --
   instruction streams live in it -- so byte-identity is the wrong test there; instead **every
   glyph point coordinate** is compared against the source, which is what "no outline was redrawn"
   actually means. Only the hinting tables (`fpgm`/`prep`/`glyf`/`loca`/`maxp`) and the metadata
   tables (`name`/`OS/2`/`head`) may differ; `STAT` and `TTFA` are the only additions. The layout
   tables carrying the ligatures and stylistic sets (`GSUB`/`GPOS`/`GDEF`), plus `cmap`, `hmtx`,
   `hhea`, `post`, `cvt ` and `gasp`, must still be byte-identical. Finally the `TTFA` table is
   read back and asserted to carry the exact ttfautohint parameters `build.py` commits to, so the
   hinting configuration cannot drift silently.
3. Structural RIBBI checks: one shared family name, correct subfamilies / weight classes / style
   bits, no JetBrains branding left in the identity strings, no NUL bytes smuggled into a name
   record, integer-PPEM `head.flags` bit, STAT present, `fvar` absent (these are statics),
   smart-dropout present in `prep`, stylistic-set UI labels still resolving, uniform advance widths
   (monospace), vertical metrics untouched and consistent across the family, Windows-only name
   records, no DSIG.
4. fontbakery `check-universal` must surface no FAIL beyond the known inherited set
   (EXPECTED_FAILS). Any *new* FAIL fails the run; the expected ones are reported but tolerated.

The EXPECTED_FAILS are inherited from upstream JetBrains Mono, not regressions introduced by the
rebrand -- verified by running the same profile over the untouched sources, where the rebrand
introduces zero new FAILs and zero new WARNs, and in fact fixes two FAILs the sources have
(`no_mac_entries`, `opentype/STAT/ital_axis`):

    case_mapping                   upstream: a few cased glyphs lack round-trip case pairs
    empty_letters                  upstream: some letter glyphs are intentionally blank
    family/win_ascent_and_descent  upstream: win metrics don't cover the full glyph bbox

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
SRC_DIR = os.path.join(REPO, FAMILY, "sources")

ITALIC, BOLD, REGULAR, USE_TYPO, WWS = 1 << 0, 1 << 5, 1 << 6, 1 << 7, 1 << 8
SMART_DROPOUT = bytes([0xB8, 0x01, 0xFF, 0x85, 0xB0, 0x04, 0x8D])

# What each stage of `build.py` is allowed to touch.
REBRANDED = {"name", "OS/2", "head"}          # metadata rewrite
REHINTED = {"fpgm", "prep", "glyf", "loca", "maxp"}   # ttfautohint output (instructions only)
ADDED = {"STAT", "TTFA"}                      # STAT by the rebrand, TTFA by ttfautohint

# Must survive byte for byte: the layout tables carrying ligatures and stylistic sets, the
# character map, the metrics, and the control values / gasp that re-hinting happens not to move.
PRESERVED = ("GDEF", "GPOS", "GSUB", "cmap", "hmtx", "hhea", "post", "cvt ", "gasp")

# The ttfautohint parameters `build.py` commits to, as they appear in the TTFA table. Asserting
# these is what stops the hinting config from drifting silently.
EXPECTED_TTFA = {
    "fallback-script": "latn",
    "gray-stem-width-mode": "quantized",
    "gdi-cleartype-stem-width-mode": "strong",
    "dw-cleartype-stem-width-mode": "quantized",
}

# Vertical metric fields that must match the source and each other -- these set line height, so
# drift between faces would make mixed-weight text jump.
VERTICAL_METRICS = (
    ("head", "unitsPerEm"),
    ("OS/2", "sTypoAscender"), ("OS/2", "sTypoDescender"), ("OS/2", "sTypoLineGap"),
    ("OS/2", "usWinAscent"), ("OS/2", "usWinDescent"),
    ("hhea", "ascender"), ("hhea", "descender"), ("hhea", "lineGap"),
)

# FAILs known to come from upstream JetBrains Mono, keyed by fontbakery check id. Anything not in
# here is treated as a regression. See the module docstring for how this set is verified.
EXPECTED_FAILS = {
    "case_mapping",
    "empty_letters",
    "family/win_ascent_and_descent",
}

# filename -> expected structural properties, including the JetBrains Mono file it was built
# from, so everything the build must not touch can be diffed against it.
SPECS = {
    "rnetonet-Regular.ttf": dict(subfamily="Regular", weight=400, bold=False, italic=False,
                                 source="JetBrainsMono-Light.ttf"),
    "rnetonet-Bold.ttf": dict(subfamily="Bold", weight=700, bold=True, italic=False,
                              source="JetBrainsMono-Regular.ttf"),
    "rnetonet-RegularItalic.ttf": dict(subfamily="Italic", weight=400, bold=False, italic=True,
                                       source="JetBrainsMono-LightItalic.ttf"),
    "rnetonet-BoldItalic.ttf": dict(subfamily="Bold Italic", weight=700, bold=True, italic=True,
                                    source="JetBrainsMono-Italic.ttf"),
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


def glyph_coordinates(path):
    """Every glyph's point coordinates (component offsets for composites).

    This is what must survive re-hinting. `glyf` bytes legitimately change -- the instruction
    stream lives in there -- but not a single coordinate may move, or an outline was redrawn.
    """
    font = TTFont(path)
    glyf = font["glyf"]
    out = {}
    for name in font.getGlyphOrder():
        glyph = glyf[name]
        glyph.expand(glyf)
        if glyph.isComposite():
            out[name] = [(c.glyphName, getattr(c, "x", 0), getattr(c, "y", 0))
                         for c in glyph.components]
        elif glyph.numberOfContours:
            out[name] = list(glyph.coordinates)
        else:
            out[name] = []
    return out


def parse_ttfa(font):
    """The TTFA table as a dict of ttfautohint parameter -> value."""
    if "TTFA" not in font:
        return {}
    text = font.getTableData("TTFA").decode("utf-8", "replace")
    out = {}
    for line in text.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def stage_scope(report):
    """Prove the build only re-hints and rebrands: no outline moves, no layout table changes."""
    print("\n== Build scope (outlines and layout must survive; only hinting + metadata change) ==")
    for fn, spec in SPECS.items():
        out_path = os.path.join(OUT_DIR, fn)
        src_path = os.path.join(SRC_DIR, spec["source"])
        font = TTFont(out_path, lazy=True)
        source = TTFont(src_path, lazy=True)
        out_tags = set(font.keys()) - {"GlyphOrder"}
        src_tags = set(source.keys()) - {"GlyphOrder"}

        report.check(out_tags - src_tags == ADDED, f"{fn}: only {sorted(ADDED)} added",
                     f"added {sorted(out_tags - src_tags)}")
        report.check(not src_tags - out_tags, f"{fn}: no source table dropped",
                     f"missing {sorted(src_tags - out_tags)}")

        changed = {t for t in out_tags & src_tags
                   if font.getTableData(t) != source.getTableData(t)}
        report.check(changed <= REBRANDED | REHINTED,
                     f"{fn}: only hinting + metadata tables changed vs {spec['source']}",
                     f"also changed {sorted(changed - REBRANDED - REHINTED)}")

        # The guarantee that survives re-hinting: not one coordinate moved.
        report.check(glyph_coordinates(out_path) == glyph_coordinates(src_path),
                     f"{fn}: every glyph outline coordinate identical to source")

        for tag in PRESERVED:
            if tag in src_tags:
                report.check(font.getTableData(tag) == source.getTableData(tag),
                             f"{fn}: {tag.strip()} byte-identical to source")

        # Re-hinting must actually have happened, and with the parameters we committed to.
        for tag in ("fpgm", "prep", "cvt "):
            report.check(len(font.getTableData(tag)) > 0, f"{fn}: {tag.strip()} present and non-empty")
        ttfa = parse_ttfa(font)
        report.check(bool(ttfa), f"{fn}: TTFA table records the hinting parameters")
        for key, want in EXPECTED_TTFA.items():
            report.check(ttfa.get(key) == want, f"{fn}: TTFA {key} == {want}",
                         f"got {ttfa.get(key)!r}")


def stage_structure(report):
    print("\n== Structural / RIBBI ==")
    families = set()
    metrics_seen = {}
    for fn, spec in SPECS.items():
        path = os.path.join(OUT_DIR, fn)
        font = TTFont(path, lazy=True)
        source = TTFont(os.path.join(SRC_DIR, spec["source"]), lazy=True)
        name, os2, head = font["name"], font["OS/2"], font["head"]

        fam = name.getDebugName(1)
        families.add(fam)
        report.check(fam == FAMILY, f"{fn}: nameID1 == '{FAMILY}'", f"got {fam!r}")
        report.check(name.getDebugName(2) == spec["subfamily"],
                     f"{fn}: nameID2 == '{spec['subfamily']}'", f"got {name.getDebugName(2)!r}")
        ps = name.getDebugName(6) or ""
        report.check(ps.startswith(f"{FAMILY}-") and " " not in ps,
                     f"{fn}: PostScript name well-formed", f"got {ps!r}")

        # The identity strings must not still say JetBrains; the attribution strings (0, 8, 9,
        # 11-14) legitimately do and are left alone. nameID 7 is the trademark line and must go.
        branded = [i for i in (1, 2, 3, 4, 6) if "jetbrains" in (name.getDebugName(i) or "").lower()]
        report.check(not branded, f"{fn}: no JetBrains branding in identity names",
                     f"nameIDs {branded} still mention it")
        report.check(name.getDebugName(7) is None, f"{fn}: trademark record (nameID 7) dropped")
        report.check(name.getDebugName(0), f"{fn}: copyright (nameID 0) preserved")
        report.check(name.getDebugName(13), f"{fn}: license (nameID 13) preserved")
        report.check(name.getDebugName(14), f"{fn}: license URL (nameID 14) preserved")

        # achVendID is NUL-padded ('JB\0\0') and str.strip() does not remove NULs, so a naive
        # rebrand smuggles them into nameID 3. Guard the whole table.
        nul = [r.nameID for r in name.names if "\x00" in str(r)]
        report.check(not nul, f"{fn}: no NUL bytes in name records", f"nameIDs {sorted(set(nul))}")

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

        # JetBrains Mono is ttfautohint-hinted (fpgm/cvt), so head.flags bit 3 must be set for
        # PPEM to round to integers -- otherwise the instructions misfire at fractional sizes.
        if "fpgm" in font or "cvt " in font:
            report.check(bool(head.flags & (1 << 3)), f"{fn}: head.flags integer-ppem bit set (hinted)")

        report.check("fvar" not in font, f"{fn}: static (no fvar)")
        report.check("STAT" in font, f"{fn}: STAT present")
        report.check("DSIG" not in font, f"{fn}: no DSIG")

        # Inherited from JetBrains Mono, not patched in -- but still required.
        prep = font["prep"].program.getBytecode() if "prep" in font else b""
        report.check(SMART_DROPOUT in prep, f"{fn}: smart-dropout instruction in prep")

        # The ssXX feature UI labels GSUB points at must still resolve after the 256+ purge.
        labels = {}
        feature_list = font["GSUB"].table.FeatureList if "GSUB" in font else None
        for record in (feature_list.FeatureRecord if feature_list else []):
            params = record.Feature.FeatureParams
            ui = getattr(params, "UINameID", None) if params else None
            if ui:
                labels[record.FeatureTag] = name.getDebugName(ui)
        report.check(labels and all(labels.values()),
                     f"{fn}: stylistic-set UI labels preserved ({len(labels)})",
                     f"unresolved: {[k for k, v in labels.items() if not v]}")

        for table, field in VERTICAL_METRICS:
            got, want = getattr(font[table], field), getattr(source[table], field)
            report.check(got == want, f"{fn}: {table}.{field} unchanged ({want})", f"got {got}")
        metrics_seen[fn] = tuple(getattr(font[t], f) for t, f in VERTICAL_METRICS)

        widths = {w for w, _ in font["hmtx"].metrics.values() if w > 0}
        report.check(len(widths) == 1, f"{fn}: monospace (uniform advance width)",
                     f"widths={sorted(widths)}")

        non_windows = [r for r in name.names if r.platformID != 3]
        report.check(not non_windows, f"{fn}: name records Windows-only",
                     f"{len(non_windows)} non-Windows records")

    report.check(families == {FAMILY}, "single shared family name across all four", f"got {families}")
    report.check({SPECS[f]["subfamily"] for f in SPECS} == {"Regular", "Bold", "Italic", "Bold Italic"},
                 "RIBBI subfamilies complete")
    report.check(len(set(metrics_seen.values())) == 1,
                 "vertical metrics identical across the family (stable line height)",
                 f"got {metrics_seen}")


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
    missing_src = [s["source"] for s in SPECS.values()
                   if not os.path.exists(os.path.join(SRC_DIR, s["source"]))]
    if missing_src:
        print(f"Sources missing: {missing_src}")
        return 1

    report = Report()
    stage_ots(report)
    stage_scope(report)
    stage_structure(report)
    stage_fontbakery(report)

    print("\n" + ("ALL CHECKS PASSED" if report.ok else "VALIDATION FAILED"))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
