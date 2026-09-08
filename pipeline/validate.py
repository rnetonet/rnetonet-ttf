"""Validate the built `rnetonet` family. Acceptance gate for `build.py`.

Five stages, each of which can fail the run (non-zero exit) so this doubles as a CI gate:

1. OTS (OpenType Sanitizer) must accept every output -- the hard "will browsers and rasterizers
   actually load this" bar.

2. Build scope. `build.py` cuts the weight axis down to the span between the Light/SemiLight
   midpoint and SemiLight, relabels that span as 400..700, and rebrands the metadata. Nothing else. Byte-identity is the
   wrong test for most tables here -- restricting a variable axis legitimately rewrites `glyf`,
   `gvar`, `cvt `, `cvar`, `hmtx`, `hhea` and the variation stores in `GDEF`/`GPOS` -- so the
   scope is proved three other ways:

     * **Outline equivalence across the whole axis.** Both the source and the output are
       instanced at matching positions (source 325/337.5/350 against output 400/550/700, the same
       three points of the same design-space span) and every glyph's every coordinate is
       compared. At the default the two must be *identical*; elsewhere they may differ by at
       most one font unit, 1/2048 em. That one unit is a floor, not a slack budget: the Regular
       is the midpoint between Cascadia's Light and SemiLight, so it is an interpolation and not
       on integer coordinates -- rebasing the default onto it must round, and the Bold deltas
       then round against that rounded default. `build.py` passes `optimize=False` to keep the
       whole axis at that floor.
     * **Hinting identity.** `fpgm`, `prep` and every glyph's instruction bytecode must be
       byte-identical to the source. `cvt `/`cvar` are exempt and must not be: those are control
       *values*, and rebasing them onto the new default through `cvar` is what a variable font's
       hinting is supposed to do. `gasp`, `cmap` and `post` must be byte-identical too.
     * **Layout parity.** Every GSUB/GPOS feature must survive with the same lookup count and
       lookup types. The one feature allowed to disappear is one that had *no* lookups at the
       default and reached the font only through `FeatureVariations` records that this cut can
       never satisfy -- upstream's `rvrn`. That is not taken on trust: the cut's span is
       normalised into the source's own design space and every condition set is proved disjoint
       from it. If a source update ever moves those conditions into range, this fails loudly.

3. Shaping equivalence, via HarfBuzz -- the check that actually matters for a coding font.
   A corpus of operators, prose, accented and combining-mark text, RTL and box drawing, plus a
   generated `base + mark` probe for every combining mark the font maps, is shaped through the
   source and through the output at both ends of the axis; the glyph *names* must match exactly
   and the positions to within the same one-unit floor. The generated probes are there because
   the prose alone left most of Cascadia's 319 GPOS mark records unexercised. Then the ligature policy is
   asserted behaviourally: this family is cut from Cascadia *Mono*, so `-> => != === <=>` and
   friends must come out as plain characters at both weights.

4. Structural / variable-font checks: `fvar` axis 400-400-700 with exactly two named instances,
   the default one reusing nameIDs 2 and 6; `STAT` with a `wght` axis (Regular linked to Bold,
   Regular elided) and an `ital` axis; RIBBI-correct names, weight class and style bits; no
   Cascadia or Microsoft branding left in the identity strings; no NUL bytes; Windows-only name
   records; no DSIG; integer-PPEM `head.flags` bit; uniform advance widths at both weights;
   vertical metrics untouched and identical across both files.

5. fontbakery `check-universal` over the family. No FAIL is tolerated beyond the known inherited
   set (EXPECTED_FAILS).

The EXPECTED_FAILS all come from upstream Cascadia Mono, not from the rebrand. That is verified,
not assumed: the same profile over the untouched sources produces the same five, and the two
stages of the build were measured separately -- restricting the axis adds one FAIL,
`fvar/regular_coords_correct` (the axis says 325 while the names still say Regular), and the
rebrand then fixes that one plus `no_mac_entries`, introducing nothing of its own.

    arabic_high_hamza              upstream: U+0674 is classed as a mark in GDEF
    case_mapping                   upstream: some cased glyphs lack round-trip case pairs
    family/win_ascent_and_descent  upstream: win metrics don't cover the full glyph bbox
    nested_components              upstream: composites whose components are themselves composites
    smart_dropout                  upstream: Cascadia is VTT-hinted, and its `prep` does not carry
                                   the ttfautohint smart-dropout instruction sequence

One WARN is also expected and is *not* inherited: `points_out_of_bounds` fires on a single glyph,
`ninepersiansuperior`, whose composite bounding box rounds a unit short of a component point once
the default sits on the midpoint. It comes from the rounding floor above, not from the rebrand --
the axis cut alone produces it, before any metadata is touched. Which glyph trips it depends on
where the default lands, so expect the name to move if the cut ever does. fontbakery's own advice
on this check is that fixing it usually does more harm than good.

Usage:
    python pipeline/validate.py
"""

import io
import json
import os
import re
import subprocess
import sys
import tempfile

import ots
import uharfbuzz as hb
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from fontTools.varLib.models import normalizeValue, piecewiseLinearMap

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAMILY = "rnetonet"
OUT_DIR = os.path.join(REPO, FAMILY)
SRC_DIR = os.path.join(REPO, FAMILY, "sources")

ITALIC, BOLD, REGULAR, USE_TYPO, WWS = 1 << 0, 1 << 5, 1 << 6, 1 << 7, 1 << 8
ELIDABLE = 0x2

SRC_REGULAR, SRC_BOLD = 325, 350
OUT_REGULAR, OUT_BOLD = 400, 700

# Fractions of the cut span to compare source against output at: both ends and the middle. The
# ends pin the two shipped instances; the middle is what proves the relabel is affine across the
# interior rather than merely correct at the two points anyone looks at.
PROBES = (0.0, 0.5, 1.0)

# The rounding floor from rebasing the default onto the midpoint, in font units at 2048 upem. Exact
# equality is required at the default itself, where no interpolation happens.
UNIT_TOLERANCE = 1

# Must survive byte for byte. `cvt `/`cvar` are deliberately absent: they carry hinting control
# *values*, which follow the default. `glyf` is absent because instruction streams live in it
# alongside coordinates -- the streams are compared separately, glyph by glyph.
PRESERVED = ("fpgm", "prep", "gasp", "cmap", "post")

# DSIG is dropped (any edit invalidates it); nothing is added.
DROPPED_TABLES = {"DSIG"}

VERTICAL_METRICS = (
    ("head", "unitsPerEm"),
    ("OS/2", "sTypoAscender"), ("OS/2", "sTypoDescender"), ("OS/2", "sTypoLineGap"),
    ("OS/2", "usWinAscent"), ("OS/2", "usWinDescent"),
    ("hhea", "ascender"), ("hhea", "descender"), ("hhea", "lineGap"),
)

EXPECTED_FAILS = {
    "arabic_high_hamza",
    "case_mapping",
    "family/win_ascent_and_descent",
    "nested_components",
    "smart_dropout",
}

# Text shaped through both the source and the output. Operators exercise `calt`, the combining
# and RTL lines exercise `mark`/`mkmk` in GPOS, and the box drawing covers the glyphs a terminal
# actually leans on.
SHAPING_CORPUS = [
    "x -> y => z != w === v <=> u |> t :: s ?. r",
    "if (a >= b && c <= d) { return a <> b; } /* -- */ // ...",
    "The quick brown fox jumps over the lazy dog 0123456789",
    "Ação, coração, JOÃO -- 0O1lI |=| <!-- --> #{} $() @[] ~~>",
    "áëo̊ũņ ÁËṓ",
    "العربية אָלֶף",
    "┌──┬──┐ │ ▓▒░ █ "
    "←↑→↓ ⇒ ∀ ∈ ℝ ≠ ≤ ≥",
]

# Sequences this family must NOT ligate: it is cut from Cascadia Mono, the ligature-free half of
# upstream. Cascadia's ligatures are monospace-preserving -- in Cascadia Code `->` stays two glyph
# slots, it just uses `hyphen_start.seq` and `greater_hyphen_end.seq` instead of `hyphen` and
# `greater` -- so counting glyphs would prove nothing. The test is whether the shaped glyphs are
# still the plain per-character ones straight out of cmap.
LIGATURE_TESTS = ("->", "=>", "!=", "===", "<=>", "|>", "::", "?.", ">=", "<-")

SPECS = {
    f"{FAMILY}-Roman.ttf": dict(
        source="CascadiaMono.ttf", subfamily="Regular", italic=False, prefix="Roman",
        instances=[("Regular", "Regular", OUT_REGULAR), ("Bold", "Bold", OUT_BOLD)]),
    f"{FAMILY}-Italic.ttf": dict(
        source="CascadiaMonoItalic.ttf", subfamily="Italic", italic=True, prefix="Italic",
        instances=[("Italic", "Italic", OUT_REGULAR), ("Bold Italic", "BoldItalic", OUT_BOLD)]),
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


def out_path(filename):
    return os.path.join(OUT_DIR, filename)


def src_path(spec):
    return os.path.join(SRC_DIR, spec["source"])


# ---------------------------------------------------------------------------- outline geometry

def pinned(path, wght):
    """The font pinned to one weight, round-tripped through a save so its coordinates have been
    rounded to integers the same way the shipped file's were. Without the round trip the source
    side compares as in-memory floats and every glyph looks like a mismatch."""
    font = instancer.instantiateVariableFont(TTFont(path), {"wght": wght}, optimize=False)
    buffer = io.BytesIO()
    font.save(buffer)
    buffer.seek(0)
    return TTFont(buffer)


def glyph_coordinates(font):
    """Every glyph's point coordinates (component offsets for composites)."""
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


def coordinate_drift(source, output):
    """(worst absolute deviation, points compared, structural mismatch) between two coordinate
    maps. A structural mismatch -- different glyphs, point counts or components -- is fatal and
    reported separately from a numeric drift."""
    if set(source) != set(output):
        return None, 0, "glyph sets differ"
    worst = points = 0
    for name, want in source.items():
        got = output[name]
        if len(want) != len(got):
            return None, points, f"{name}: {len(want)} points vs {len(got)}"
        for a, b in zip(want, got):
            points += 1
            if isinstance(a[0], str):                    # composite component
                if a[0] != b[0]:
                    return None, points, f"{name}: component {a[0]} vs {b[0]}"
                worst = max(worst, abs(a[1] - b[1]), abs(a[2] - b[2]))
            else:
                worst = max(worst, abs(a[0] - b[0]), abs(a[1] - b[1]))
    return worst, points, None


NUMERIC_VALUE = re.compile(r'value="(-?\d+)"')


def gpos_dump(font):
    """GPOS as XML. Only meaningful on a *fully instanced* font, where every Device/VariationIndex
    table has been resolved away -- on the variable originals the two sides carry different
    variation data and would never compare."""
    if "GPOS" not in font:
        return ""
    buffer = io.StringIO()
    font.saveXML(buffer, tables=["GPOS"])
    return buffer.getvalue()


def positioning_drift(source, output):
    """(worst absolute deviation, values differing, structural mismatch) between two GPOS dumps.

    Lines may differ only in a single numeric `value="N"`. Anything else -- a different tag, a
    different attribute, a different line count -- is a structural change and fails outright."""
    left, right = source.splitlines(), output.splitlines()
    if len(left) != len(right):
        return None, 0, f"{len(left)} lines vs {len(right)}"
    worst = differing = 0
    for a, b in zip(left, right):
        if a == b:
            continue
        got, want = NUMERIC_VALUE.search(a), NUMERIC_VALUE.search(b)
        if not (got and want) or NUMERIC_VALUE.sub("", a) != NUMERIC_VALUE.sub("", b):
            return None, differing, f"non-numeric difference: {a.strip()!r} vs {b.strip()!r}"
        worst = max(worst, abs(int(got.group(1)) - int(want.group(1))))
        differing += 1
    return worst, differing, None


def instruction_streams(font):
    glyf = font["glyf"]
    out = {}
    for name in font.getGlyphOrder():
        glyph = glyf[name]
        glyph.expand(glyf)
        program = getattr(glyph, "program", None)
        out[name] = program.getBytecode() if program is not None else b""
    return out


# ------------------------------------------------------------------------------ layout parity

def feature_shapes(font, tag):
    """{feature tag: (lookup count, lookup types)} -- enough to catch a feature losing lookups or
    having them swapped out, without depending on lookup *indices*, which legitimately shift when
    unreachable lookups are pruned."""
    if tag not in font:
        return {}
    table = font[tag].table
    lookups = table.LookupList.Lookup if table.LookupList else []
    out = {}
    for record in table.FeatureList.FeatureRecord:
        indices = list(record.Feature.LookupListIndex)
        shape = (len(indices), tuple(lookups[i].LookupType for i in indices))
        out.setdefault(record.FeatureTag, set()).add(shape)
    return out


def cut_span_in_source_design_space(source):
    """Where the cut sits in the *source's* normalised design space, after `avar`.

    Feature-variation condition sets are expressed in exactly these coordinates, so this is what
    they have to be disjoint from for the cut to be unable to trigger them."""
    axis = next(a for a in source["fvar"].axes if a.axisTag == "wght")
    triple = (axis.minValue, axis.defaultValue, axis.maxValue)
    segments = source["avar"].segments.get("wght", {}) if "avar" in source else {}
    span = []
    for value in (SRC_REGULAR, SRC_BOLD):
        normalized = normalizeValue(value, triple)
        span.append(piecewiseLinearMap(normalized, segments) if segments else normalized)
    return min(span), max(span)


def unreachable_condition_sets(source, tag):
    """One bool per FeatureVariations record in `tag`: can the cut ever satisfy it?

    A condition set fires only when *all* its conditions hold, so a single condition whose range
    does not overlap the cut's span makes the whole set unreachable."""
    table = source[tag].table if tag in source else None
    variations = getattr(table, "FeatureVariations", None) if table else None
    if not variations:
        return []
    lo, hi = cut_span_in_source_design_space(source)
    axes = [a.axisTag for a in source["fvar"].axes]
    return [
        any(axes[c.AxisIndex] == "wght"
            and (c.FilterRangeMaxValue < lo or c.FilterRangeMinValue > hi)
            for c in record.ConditionSet.ConditionTable)
        for record in variations.FeatureVariationRecord
    ]


def variation_only_features(source, tag):
    """Feature tags that carry no lookups at the default and appear only via FeatureVariations --
    the only tags whose disappearance a range restriction can justify."""
    table = source[tag].table if tag in source else None
    if table is None:
        return set()
    empty = {r.FeatureTag for r in table.FeatureList.FeatureRecord
             if not r.Feature.LookupListIndex}
    variations = getattr(table, "FeatureVariations", None)
    substituted = set()
    if variations:
        for record in variations.FeatureVariationRecord:
            for sub in record.FeatureTableSubstitution.SubstitutionRecord:
                substituted.add(table.FeatureList.FeatureRecord[sub.FeatureIndex].FeatureTag)
    return empty & substituted


# ------------------------------------------------------------------------------------- shaping

def shape(path, text, wght):
    blob = hb.Blob.from_file_path(path)
    font = hb.Font(hb.Face(blob))
    font.set_variations({"wght": wght})
    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.guess_segment_properties()
    hb.shape(font, buffer)
    return [(font.get_glyph_name(info.codepoint), pos.x_advance, pos.x_offset, pos.y_offset)
            for info, pos in zip(buffer.glyph_infos, buffer.glyph_positions)]


def mark_probes(font):
    """`base + combining mark` for every mark the font maps, so the shaping stage exercises GPOS
    anchors broadly instead of relying on whichever ones the prose corpus happens to touch.

    This exists because it was measured: the prose corpus alone reaches only a couple of mark
    anchors, and moving one of Cascadia's 319 mark records by 40 units went undetected. 53 marks
    are reachable through cmap; pairing each with two different bases covers them."""
    cmap = font.getBestCmap()
    gdef = font["GDEF"].table if "GDEF" in font else None
    classes = gdef.GlyphClassDef.classDefs if gdef and gdef.GlyphClassDef else {}
    codepoint = {}
    for cp, glyph in cmap.items():
        codepoint.setdefault(glyph, cp)
    marks = sorted(codepoint[g] for g, c in classes.items() if c == 3 and g in codepoint)
    return [base + chr(cp) for cp in marks for base in ("a", "O")]


def plain_glyph_names(font, text):
    """What `text` shapes to with no substitutions at all: one glyph per character, straight out
    of cmap. This is what an unligated font must produce."""
    cmap = font.getBestCmap()
    return [cmap.get(ord(character)) for character in text]


# -------------------------------------------------------------------------------------- stages

def stage_ots(report):
    print("\n== OTS sanitize ==")
    for filename in SPECS:
        result = ots.sanitize(out_path(filename), capture_output=True, text=True)
        detail = (result.stdout or "") + (result.stderr or "")
        report.check(result.returncode == 0, f"{filename} sanitizes", detail.strip())


def stage_scope(report):
    print("\n== Build scope (the cut is a slice of upstream's design space, relabelled) ==")
    for filename, spec in SPECS.items():
        font = TTFont(out_path(filename), lazy=True)
        source = TTFont(src_path(spec), lazy=True)
        out_tags = set(font.keys()) - {"GlyphOrder"}
        src_tags = set(source.keys()) - {"GlyphOrder"}

        report.check(not out_tags - src_tags, f"{filename}: no table added",
                     f"added {sorted(out_tags - src_tags)}")
        report.check(src_tags - out_tags == DROPPED_TABLES,
                     f"{filename}: only {sorted(DROPPED_TABLES)} dropped",
                     f"dropped {sorted(src_tags - out_tags)}")

        for tag in PRESERVED:
            if tag in src_tags:
                report.check(font.getTableData(tag) == source.getTableData(tag),
                             f"{filename}: {tag.strip()} byte-identical to source")

        report.check(font.getGlyphOrder() == source.getGlyphOrder(),
                     f"{filename}: glyph order unchanged")

        # Hinting: the program is untouched, only the control values it reads follow the default.
        full_out = TTFont(out_path(filename))
        full_src = TTFont(src_path(spec))
        streams_out = instruction_streams(full_out)
        streams_src = instruction_streams(full_src)
        differing = [g for g in streams_src if streams_src[g] != streams_out.get(g)]
        hinted = sum(1 for g in streams_src if streams_src[g])
        report.check(not differing,
                     f"{filename}: all {hinted} glyph instruction streams byte-identical",
                     f"{len(differing)} differ, e.g. {differing[:5]}")
        report.check(len(font.getTableData("cvt ")) > 0 and "cvar" in font,
                     f"{filename}: cvt/cvar present (hinting still varies with weight)")

        # Outlines and positioning: the same slice of the same design space, under new labels.
        for fraction in PROBES:
            source_at = SRC_REGULAR + fraction * (SRC_BOLD - SRC_REGULAR)
            output_at = OUT_REGULAR + fraction * (OUT_BOLD - OUT_REGULAR)
            limit = 0 if fraction == 0.0 else UNIT_TOLERANCE
            source_pin = pinned(src_path(spec), source_at)
            output_pin = pinned(out_path(filename), output_at)

            drift, points, broken = coordinate_drift(glyph_coordinates(source_pin),
                                                     glyph_coordinates(output_pin))
            if broken:
                report.check(False, f"{filename}: outlines at src {source_at:g} / out {output_at:g}",
                             broken)
            else:
                report.check(drift <= limit,
                             f"{filename}: {points} coordinates at out {output_at:g} match src "
                             f"{source_at:g} within {limit} unit(s) (worst {drift})",
                             f"worst deviation {drift}")

            # Every GPOS value, compared on the fully instanced tables where no variation data is
            # left to explain a difference away. This covers all 319 mark records, including the
            # ~half that no shaping probe can reach -- `uniFBBC.comb` and the other Arabic
            # contextual marks have no cmap entry, so only a direct table comparison sees them.
            drift, values, broken = positioning_drift(gpos_dump(source_pin), gpos_dump(output_pin))
            if broken:
                report.check(False, f"{filename}: GPOS at src {source_at:g} / out {output_at:g}",
                             broken)
            else:
                report.check(drift <= limit,
                             f"{filename}: GPOS at out {output_at:g} matches src {source_at:g} "
                             f"within {limit} unit(s) ({values} values differ, worst {drift})",
                             f"worst deviation {drift}")

        # Layout: every feature keeps its lookups, and the only tag allowed to vanish is one that
        # was unreachable in this span to begin with.
        for tag in ("GSUB", "GPOS"):
            want = feature_shapes(full_src, tag)
            got = feature_shapes(full_out, tag)
            vanished = set(want) - set(got)
            justified = variation_only_features(full_src, tag)
            report.check(vanished <= justified,
                         f"{filename}: {tag} features kept ({len(got)}/{len(want)})",
                         f"lost {sorted(vanished - justified)}")
            changed = {t for t in set(want) & set(got) if want[t] != got[t]}
            report.check(not changed, f"{filename}: {tag} lookup counts and types unchanged",
                         f"changed {sorted(changed)}")
            report.check(not set(got) - set(want), f"{filename}: {tag} gained no feature",
                         f"gained {sorted(set(got) - set(want))}")

            reachability = unreachable_condition_sets(full_src, tag)
            if reachability:
                lo, hi = cut_span_in_source_design_space(full_src)
                report.check(all(reachability),
                             f"{filename}: all {len(reachability)} {tag} feature-variation "
                             f"condition sets are disjoint from the cut "
                             f"[{lo:.5f}, {hi:.5f}]",
                             "a condition set overlaps the shipped range -- dropping it silently "
                             "would change shaping")


def stage_shaping(report):
    print("\n== Shaping (HarfBuzz: same glyphs, same positions, and the right ligature policy) ==")
    for filename, spec in SPECS.items():
        output, source = out_path(filename), src_path(spec)
        corpus = SHAPING_CORPUS + mark_probes(TTFont(output, lazy=True))
        for fraction in (0.0, 1.0):
            source_at = SRC_REGULAR + fraction * (SRC_BOLD - SRC_REGULAR)
            output_at = OUT_REGULAR + fraction * (OUT_BOLD - OUT_REGULAR)
            names_ok, worst, count = True, 0, 0
            for text in corpus:
                want = shape(source, text, source_at)
                got = shape(output, text, output_at)
                if [g[0] for g in want] != [g[0] for g in got]:
                    names_ok = False
                    break
                for a, b in zip(want, got):
                    count += 1
                    worst = max(worst, abs(a[1] - b[1]), abs(a[2] - b[2]), abs(a[3] - b[3]))
            limit = 0 if fraction == 0.0 else UNIT_TOLERANCE
            report.check(names_ok,
                         f"{filename}: shaping at out {output_at:g} picks the same {count} glyphs "
                         f"as src {source_at:g}")
            report.check(names_ok and worst <= limit,
                         f"{filename}: shaped positions at out {output_at:g} within {limit} "
                         f"unit(s) of src {source_at:g} (worst {worst})")

        font = TTFont(output, lazy=True)
        ligated = []
        for text in LIGATURE_TESTS:
            expected = plain_glyph_names(font, text)
            for wght in (OUT_REGULAR, OUT_BOLD):
                if [g[0] for g in shape(output, text, wght)] != expected:
                    ligated.append((text, wght))
        report.check(not ligated,
                     f"{filename}: leaves all {len(LIGATURE_TESTS)} sequences unligated "
                     f"at both weights",
                     f"ligated: {ligated}")


def stage_structure(report):
    print("\n== Structural / variable-font ==")
    metrics_seen = {}
    for filename, spec in SPECS.items():
        font = TTFont(out_path(filename), lazy=True)
        source = TTFont(src_path(spec), lazy=True)
        name, os2, head = font["name"], font["OS/2"], font["head"]

        report.check(name.getDebugName(1) == FAMILY, f"{filename}: nameID1 == '{FAMILY}'",
                     f"got {name.getDebugName(1)!r}")
        report.check(name.getDebugName(2) == spec["subfamily"],
                     f"{filename}: nameID2 == '{spec['subfamily']}'",
                     f"got {name.getDebugName(2)!r}")
        report.check(name.getDebugName(4) == f"{FAMILY} {spec['subfamily']}",
                     f"{filename}: nameID4 == '{FAMILY} {spec['subfamily']}'",
                     f"got {name.getDebugName(4)!r}")
        ps = name.getDebugName(6) or ""
        report.check(ps == f"{FAMILY}-{spec['subfamily'].replace(' ', '')}" and " " not in ps,
                     f"{filename}: PostScript name well-formed", f"got {ps!r}")
        prefix = name.getDebugName(25) or ""
        report.check(prefix == f"{FAMILY}{spec['prefix']}" and prefix.isalnum(),
                     f"{filename}: variations PostScript prefix (nameID 25) well-formed",
                     f"got {prefix!r}")

        # The identity strings must not still say Cascadia or Microsoft. The attribution strings
        # (0, 8, 9, 11-14) legitimately do and are left alone; 7 is the trademark and must go.
        branded = [i for i in (1, 2, 3, 4, 6, 25)
                   if re.search(r"cascadia|microsoft", name.getDebugName(i) or "", re.I)]
        report.check(not branded, f"{filename}: no Cascadia/Microsoft branding in identity names",
                     f"nameIDs {branded} still mention it")
        report.check(name.getDebugName(7) is None, f"{filename}: trademark (nameID 7) dropped")
        for name_id, what in ((0, "copyright"), (13, "license"), (14, "license URL"),
                              (8, "manufacturer"), (9, "designer")):
            kept = name.getDebugName(name_id)
            report.check(kept and kept == source["name"].getDebugName(name_id),
                         f"{filename}: {what} (nameID {name_id}) preserved verbatim",
                         f"got {kept!r}")

        nul = [r.nameID for r in name.names if "\x00" in str(r)]
        report.check(not nul, f"{filename}: no NUL bytes in name records",
                     f"nameIDs {sorted(set(nul))}")
        non_windows = [r for r in name.names if r.platformID != 3]
        report.check(not non_windows, f"{filename}: name records Windows-only",
                     f"{len(non_windows)} non-Windows records")

        # fvar: one axis, cut to the two shipped weights.
        fvar = font["fvar"]
        axis_tags = [a.axisTag for a in fvar.axes]
        report.check(axis_tags == ["wght"], f"{filename}: single wght axis", f"got {axis_tags}")
        axis = fvar.axes[0]
        report.check((axis.minValue, axis.defaultValue, axis.maxValue)
                     == (OUT_REGULAR, OUT_REGULAR, OUT_BOLD),
                     f"{filename}: wght axis {OUT_REGULAR}-{OUT_REGULAR}-{OUT_BOLD}",
                     f"got {axis.minValue}-{axis.defaultValue}-{axis.maxValue}")
        report.check(name.getDebugName(axis.axisNameID) == "Weight",
                     f"{filename}: wght axis name resolves",
                     f"got {name.getDebugName(axis.axisNameID)!r}")

        report.check(len(fvar.instances) == len(spec["instances"]),
                     f"{filename}: exactly {len(spec['instances'])} named instances",
                     f"got {len(fvar.instances)}")
        for instance, (style, ps_suffix, wght) in zip(fvar.instances, spec["instances"]):
            report.check(instance.coordinates == {"wght": wght}
                         and name.getDebugName(instance.subfamilyNameID) == style
                         and name.getDebugName(instance.postscriptNameID) == f"{FAMILY}-{ps_suffix}",
                         f"{filename}: instance '{style}' at wght {wght} "
                         f"-> {FAMILY}-{ps_suffix}",
                         f"got {name.getDebugName(instance.subfamilyNameID)!r} "
                         f"{instance.coordinates} "
                         f"ps={name.getDebugName(instance.postscriptNameID)!r}")
        default = fvar.instances[0]
        report.check((default.subfamilyNameID, default.postscriptNameID) == (2, 6),
                     f"{filename}: default instance reuses nameIDs 2 and 6",
                     f"got {default.subfamilyNameID}/{default.postscriptNameID}")

        # STAT: Regular elided and linked to Bold, plus the ital axis this file sits on.
        stat = font["STAT"].table
        stat_axes = [a.AxisTag for a in stat.DesignAxisRecord.Axis]
        report.check(stat_axes == ["wght", "ital"], f"{filename}: STAT axes wght+ital",
                     f"got {stat_axes}")
        values = {}
        for value in (stat.AxisValueArray.AxisValue if stat.AxisValueArray else []):
            values[name.getDebugName(value.ValueNameID)] = (
                stat_axes[value.AxisIndex], getattr(value, "Value", None),
                getattr(value, "LinkedValue", None), value.Flags)
        report.check(values.get("Regular") == ("wght", OUT_REGULAR, OUT_BOLD, ELIDABLE),
                     f"{filename}: STAT Regular at {OUT_REGULAR}, elided, linked to {OUT_BOLD}",
                     f"got {values.get('Regular')}")
        report.check(values.get("Bold") == ("wght", OUT_BOLD, None, 0),
                     f"{filename}: STAT Bold at {OUT_BOLD}", f"got {values.get('Bold')}")
        if spec["italic"]:
            report.check(values.get("Italic") == ("ital", 1, None, 0),
                         f"{filename}: STAT ital == 1 (Italic, not elided)",
                         f"got {values.get('Italic')}")
        else:
            report.check(values.get("Roman") == ("ital", 0, 1, ELIDABLE),
                         f"{filename}: STAT ital == 0 (Roman, elided, linked to Italic)",
                         f"got {values.get('Roman')}")

        # Weight class and style bits: the default instance is the Regular, so nothing is bold.
        report.check(os2.usWeightClass == OUT_REGULAR,
                     f"{filename}: usWeightClass == {OUT_REGULAR}", f"got {os2.usWeightClass}")
        selection = os2.fsSelection
        report.check(not selection & BOLD, f"{filename}: fsSelection BOLD clear (Bold is on the axis)")
        report.check(bool(selection & ITALIC) == spec["italic"],
                     f"{filename}: fsSelection ITALIC == {spec['italic']}")
        report.check(bool(selection & REGULAR) == (not spec["italic"]),
                     f"{filename}: fsSelection REGULAR correct")
        report.check(bool(selection & USE_TYPO), f"{filename}: fsSelection USE_TYPO_METRICS set")
        report.check(bool(selection & WWS), f"{filename}: fsSelection WWS set")
        report.check(not head.macStyle & 0b01, f"{filename}: macStyle bold bit clear")
        report.check(bool(head.macStyle & 0b10) == spec["italic"],
                     f"{filename}: macStyle italic bit == {spec['italic']}")

        # Cascadia is TrueType-hinted, so PPEM must round to integers or the instructions misfire.
        report.check(bool(head.flags & (1 << 3)), f"{filename}: head.flags integer-ppem bit set")
        report.check("DSIG" not in font, f"{filename}: no DSIG")
        report.check("gvar" in font, f"{filename}: still variable (gvar present)")

        # Timestamps come from the source rather than the wall clock. This is what makes the
        # build byte-reproducible -- `head.modified` was the only table that differed between two
        # runs before `build.py` started passing recalcTimestamp=False.
        for field in ("created", "modified"):
            report.check(getattr(head, field) == getattr(source["head"], field),
                         f"{filename}: head.{field} inherited from source (reproducible build)",
                         f"got {getattr(head, field)} vs {getattr(source['head'], field)}")

        for table, field in VERTICAL_METRICS:
            got, want = getattr(font[table], field), getattr(source[table], field)
            report.check(got == want, f"{filename}: {table}.{field} unchanged ({want})",
                         f"got {got}")
        metrics_seen[filename] = tuple(getattr(font[t], f) for t, f in VERTICAL_METRICS)

        # Monospace has to hold at both ends of the axis, not just at the default.
        for wght in (OUT_REGULAR, OUT_BOLD):
            instance = instancer.instantiateVariableFont(TTFont(out_path(filename)),
                                                         {"wght": wght}, optimize=False)
            widths = {w for w, _ in instance["hmtx"].metrics.values() if w > 0}
            report.check(len(widths) == 1,
                         f"{filename}: monospace at wght {wght} (uniform advance)",
                         f"widths={sorted(widths)}")

    report.check(len(metrics_seen) == 2, f"{FAMILY}: roman + italic both present",
                 f"got {sorted(metrics_seen)}")
    report.check(len(set(metrics_seen.values())) == 1,
                 "vertical metrics identical across the family (stable line height)",
                 f"got {metrics_seen}")


def _check_id(check):
    match = re.search(r"<FontBakeryCheck:([^>]+)>", check["key"][1])
    return match.group(1) if match else check["key"][1]


def stage_fontbakery(report):
    print("\n== fontbakery check-universal (FAIL level) ==")
    fonts = [out_path(filename) for filename in SPECS]
    with tempfile.TemporaryDirectory() as tmp:
        json_path = os.path.join(tmp, "fb.json")
        subprocess.run(
            [sys.executable, "-m", "fontbakery", "check-universal",
             "--loglevel", "FAIL", "--no-progress", "-C", "--json", json_path, *fonts],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        with open(json_path, encoding="utf-8") as handle:
            data = json.load(handle)

    unexpected, expected_seen = {}, {}
    for section in data["sections"]:
        for check in section["checks"]:
            if check["result"] != "FAIL":
                continue
            cid = _check_id(check)
            filename = os.path.basename(check.get("filename") or "<family>")
            bucket = expected_seen if cid in EXPECTED_FAILS else unexpected
            bucket.setdefault(cid, []).append(filename)

    counts = data["result"]
    print(f"  totals: PASS={counts.get('PASS')} FAIL={counts.get('FAIL')} "
          f"WARN={counts.get('WARN')} SKIP={counts.get('SKIP')} INFO={counts.get('INFO')}")
    for cid in sorted(expected_seen):
        print(f"    [expected FAIL] {cid} ({len(expected_seen[cid])} files)")
    for cid in sorted(unexpected):
        print(f"    [UNEXPECTED FAIL] {cid}: {', '.join(unexpected[cid])}")
    report.check(not unexpected, "no fontbakery FAIL beyond the expected/inherited set")


def main():
    missing = [f for f in SPECS if not os.path.exists(out_path(f))]
    if missing:
        print(f"Outputs missing: {missing}\nRun `python pipeline/build.py` first.")
        return 1
    missing_src = [s["source"] for s in SPECS.values() if not os.path.exists(src_path(s))]
    if missing_src:
        print(f"Sources missing: {sorted(set(missing_src))}")
        return 1

    report = Report()
    stage_ots(report)
    stage_scope(report)
    stage_shaping(report)
    stage_structure(report)
    stage_fontbakery(report)

    print("\n" + ("ALL CHECKS PASSED" if report.ok else "VALIDATION FAILED"))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
