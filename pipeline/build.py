"""Build the `rnetonet` family by instancing and hinting the JetBrains Mono variable fonts.

`rnetonet` is a rebrand of **JetBrains Mono** (kept intact, coding ligatures included). The four
RIBBI styles are produced by pinning the `wght` axis of JetBrains Mono's variable fonts, so the
whole family derives from two source files:

    rnetonet/sources/JetBrains_Mono/JetBrainsMono[wght].ttf         @ wght=325 (Light..Regular) -> rnetonet-Regular.ttf        (-> 400)
    rnetonet/sources/JetBrains_Mono/JetBrainsMono[wght].ttf         @ wght=375 (Light..Regular) -> rnetonet-Bold.ttf           (-> 700)
    rnetonet/sources/JetBrains_Mono/JetBrainsMono-Italic[wght].ttf  @ wght=325 (Light..Regular) -> rnetonet-RegularItalic.ttf  (-> 400)
    rnetonet/sources/JetBrains_Mono/JetBrainsMono-Italic[wght].ttf  @ wght=375 (Light..Regular) -> rnetonet-BoldItalic.ttf     (-> 700)

The Regular is pinned at wght 325 and the Bold at wght 375 -- both custom values between
JetBrains' Light (300) and Regular (400) named instances (instancing accepts any axis value, not
just named ones). The lighter pin ships as the family's Regular (usWeightClass 400) and the
heavier as its Bold (700). That is a deliberately low-contrast pairing (only 50 axis units apart),
so the four files still form one RIBBI family that bold- and italic-links correctly.

Per style the pipeline is: instance -> **ttfautohint** -> rebrand. JetBrains' variable fonts ship
without TrueType instructions (no `fpgm`/`cvt`, only a `gasp` and a smart-dropout `prep`), so the
pinned instance is effectively unhinted and leans entirely on the rasterizer -- which reads soft
on Windows/DirectWrite (VS Code). We run ttfautohint over each instance to add a full auto-hinted
instruction set (fpgm/prep/cvt + per-glyph programs) tuned aggressively for Windows: hinting range
8..96 ppem with no upper limit, Windows blue zones, latin fallback so symbols/box-drawing are
hinted too, *strong* stem-width snapping for grayscale and GDI ClearType, and *quantized* snapping
for DirectWrite ClearType (VS Code) so stems stay crisp while keeping the design weight faithful.
A `TTFA` table records the exact options used.

Only after hinting do we rewrite naming, weight/style flags, STAT and vertical metrics. Glyph
outlines and the layout tables (GSUB/GPOS, hence JetBrains Mono's `calt`/`liga` ligatures) are
never touched; ttfautohint adds instructions and a gasp/cvt/fpgm/prep, and owns `head.flags`.

OFL compliance: copyright (nameID 0), full license (13), license URL (14) and author
acknowledgements (8/9) are preserved; the reserved name is dropped by renaming the family
(OFL clause 3) and the trademark line (7) is dropped. No license text is altered (clause 5).

Usage:
    python pipeline/build.py

Requires `ttfautohint-py` (bundles the ttfautohint library) alongside `fonttools`.
Run `python pipeline/validate.py` afterwards to sanity-check the four outputs.
"""

import io
import os

from fontTools.otlLib.builder import buildStatTable
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from ttfautohint import ttfautohint
from ttfautohint.options import StemWidthMode

# Repo root, resolved from this file so the pipeline runs from any working directory.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAMILY = "rnetonet"
SRC_DIR = os.path.join(REPO, FAMILY, "sources", "JetBrains_Mono")
OUT_DIR = os.path.join(REPO, FAMILY)
WINDOWS = (3, 1, 0x409)

ITALIC, BOLD, REGULAR, USE_TYPO, WWS = 1 << 0, 1 << 5, 1 << 6, 1 << 7, 1 << 8
ELIDABLE = 0x2

# JetBrains Mono's native vertical metrics (upem 1000), shared across every weight. Kept as the
# designer set them so line height is stable across the four styles. ttfautohint reads these to
# build its Windows-compatibility blue zones, so setting them here (== the source's own values)
# stays consistent with the hinting.
WIN_ASCENT, WIN_DESCENT = 1165, 400

# ttfautohint options -- tuned to hint as hard as is sensible for Windows/DirectWrite (VS Code).
# STRONG stem width for grayscale and GDI ClearType snaps stems to whole pixels; DirectWrite
# ClearType (VS Code) uses QUANTIZED so stems stay crisp without over-thickening the design weight;
# latin default+fallback extends hinting to symbols/box-drawing; range 8..96 with no upper limit
# keeps hints live at every size; a TTFA table records the options.
STRONG = StemWidthMode.STRONG
QUANTIZED = StemWidthMode.QUANTIZED
TTFAUTOHINT_OPTIONS = dict(
    hinting_range_min=8,
    hinting_range_max=96,
    hinting_limit=0,  # 0 == no upper ppem limit: hints stay active at all sizes
    increase_x_height=14,
    windows_compatibility=True,
    default_script="latn",
    fallback_script="latn",
    hint_composites=True,
    gray_stem_width_mode=STRONG,
    gdi_cleartype_stem_width_mode=STRONG,
    dw_cleartype_stem_width_mode=QUANTIZED,
    TTFA_info=True,
)

# Smart-dropout control: PUSHW[] 511; SCANCTRL[]; PUSHB[] 4; SCANTYPE[]. ttfautohint already emits
# this exact sequence in the `prep` it generates, so the guard below is a defensive no-op here; it
# stays so the pipeline still satisfies fontbakery's `opentype/smart_dropout` if a future hinting
# path ever omitted it.
SMART_DROPOUT = bytes([0xB8, 0x01, 0xFF, 0x85, 0xB0, 0x04, 0x8D])

# Names that describe JetBrains Mono and must not survive the rename. 1-6 are rewritten;
# 7 is the trademark line; 16/17 are the typographic family/subfamily; 25 is the variations
# PostScript name prefix (dead once instanced).
DROP_IDS = {1, 2, 3, 4, 5, 6, 7, 16, 17, 18, 20, 21, 22, 25}

# IDs 256+ hold both the variable-axis / named-instance labels (dead once instanced) and the
# stylistic-set UI labels that GSUB still points at. Dropping the whole range would orphan the
# latter, so collect what the layout tables reference and keep exactly those -- this is also
# what preserves the ligature/stylistic-set feature UI.
FEATURE_NAME_ATTRS = (
    "UINameID",
    "FeatUILabelNameID",
    "FeatUITooltipTextNameID",
    "SampleTextNameID",
    "FirstParamUILabelNameID",
)


def referenced_name_ids(font):
    ids = set()
    for tag in ("GSUB", "GPOS"):
        if tag not in font:
            continue
        feature_list = font[tag].table.FeatureList
        if not feature_list:
            continue
        for record in feature_list.FeatureRecord:
            params = record.Feature.FeatureParams
            if params is None:
                continue
            for attr in FEATURE_NAME_ATTRS:
                value = getattr(params, attr, None)
                if value:
                    ids.add(value)
    return ids


def autohint(font):
    """Serialize `font`, run ttfautohint over it, and return the hinted TTFont."""
    buf = io.BytesIO()
    font.save(buf)
    hinted = ttfautohint(in_buffer=buf.getvalue(), **TTFAUTOHINT_OPTIONS)
    return TTFont(io.BytesIO(hinted))


def patch_smart_dropout(font):
    """Append the smart-dropout instruction to `prep` if it is not already present."""
    if "prep" not in font:
        return False
    program = font["prep"].program
    bytecode = program.getBytecode()
    if SMART_DROPOUT in bytecode:
        return False
    program.fromBytecode(bytecode + SMART_DROPOUT)
    return True


REGULAR_WGHT = dict(value=400, name="Regular", flags=ELIDABLE, linkedValue=700)
BOLD_WGHT = dict(value=700, name="Bold")
ROMAN_ITAL = dict(value=0, name="Roman", flags=ELIDABLE, linkedValue=1)
ITALIC_ITAL = dict(value=1, name="Italic")

ROMAN = "JetBrainsMono[wght].ttf"
ITAL = "JetBrainsMono-Italic[wght].ttf"

BUILDS = [
    # src, wght, outfile, subfamily, ps suffix, weightclass, bold, italic, stat wght, stat ital
    (ROMAN, 325, "rnetonet-Regular.ttf", "Regular", "Regular", 400, False, False, REGULAR_WGHT, ROMAN_ITAL),
    (ROMAN, 375, "rnetonet-Bold.ttf", "Bold", "Bold", 700, True, False, BOLD_WGHT, ROMAN_ITAL),
    (ITAL, 325, "rnetonet-RegularItalic.ttf", "Italic", "Italic", 400, False, True, REGULAR_WGHT, ITALIC_ITAL),
    (ITAL, 375, "rnetonet-BoldItalic.ttf", "Bold Italic", "BoldItalic", 700, True, True, BOLD_WGHT, ITALIC_ITAL),
]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    for src, wght, out, subfamily, ps_suffix, weight_class, bold, italic, stat_w, stat_i in BUILDS:
        instance = instancer.instantiateVariableFont(
            TTFont(os.path.join(SRC_DIR, src)), {"wght": wght}, inplace=True, updateFontNames=False
        )
        # Hint the pinned instance before any metadata surgery, so the rebrand can't be clobbered
        # by ttfautohint and ttfautohint sees the untouched outlines/metrics.
        font = autohint(instance)
        name, os2, head = font["name"], font["OS/2"], font["head"]

        # Read source version/unique-id parts before the drop step removes them.
        version = name.getDebugName(5) or "Version 1.000"
        id3 = name.getDebugName(3) or ""
        ver_num = id3.split(";")[0] if id3.split(";")[0] else version.replace("Version ", "").split(";")[0].strip()
        ps_name = f"{FAMILY}-{ps_suffix}"
        vend = os2.achVendID.strip()

        keep = referenced_name_ids(font)
        drop = DROP_IDS | {i for i in range(256, 32768) if i not in keep}
        name.names = [r for r in name.names if r.nameID not in drop]
        for name_id, value in (
            (1, FAMILY),
            (2, subfamily),
            (3, f"{ver_num};{vend};{ps_name}"),
            (4, f"{FAMILY} {subfamily}"),
            (5, version),
            (6, ps_name),
        ):
            name.setName(value, name_id, *WINDOWS)

        os2.usWeightClass = weight_class
        os2.fsSelection = (os2.fsSelection & ~(ITALIC | BOLD | REGULAR)) | WWS
        os2.fsSelection |= (BOLD if bold else 0) | (ITALIC if italic else 0)
        if not bold and not italic:
            os2.fsSelection |= REGULAR

        # Declare a proper monospace PANOSE: Latin Text (2), monospaced (bProportion 9).
        os2.panose.bFamilyType = 2
        os2.panose.bProportion = 9
        os2.panose.bWeight = 8 if bold else 5

        head.macStyle = (head.macStyle & ~0b11) | (0b1 if bold else 0) | (0b10 if italic else 0)
        # Force integer PPEM (head.flags bit 3). The font is now TrueType-hinted, and hints assume
        # whole-pixel sizes -- at fractional ppem (as DirectWrite can request) the instructions
        # misfire. ttfautohint leaves this bit clear, so we set it: it makes the hinting land
        # cleanly in VS Code and satisfies fontbakery's `integer_ppem_if_hinted`.
        head.flags |= 1 << 3

        os2.usWinAscent, os2.usWinDescent = WIN_ASCENT, WIN_DESCENT

        patch_smart_dropout(font)

        buildStatTable(
            font,
            [
                dict(tag="wght", name="Weight", ordering=0, values=[stat_w]),
                dict(tag="ital", name="Italic", ordering=1, values=[stat_i]),
            ],
            elidedFallbackName="Regular",
        )

        # buildStatTable adds Mac-platform records for its own names; strip after it runs so
        # the name table stays Windows-only like the source.
        name.names = [r for r in name.names if r.platformID != 1]

        if "DSIG" in font:
            del font["DSIG"]

        glyf = font["glyf"]
        hinted_glyphs = sum(
            1 for gname in glyf.keys()
            if getattr(glyf[gname], "program", None) and len(glyf[gname].program.getBytecode()) > 0
        )

        font.save(os.path.join(OUT_DIR, out))
        print(
            f"{src:<28} @wght={wght} -> {out:<28} w={weight_class} "
            f"typo={'Y' if os2.fsSelection & USE_TYPO else 'n'} "
            f"hinted={hinted_glyphs}/{len(glyf.keys())} "
            f"ttfa={'TTFA' in font} fvar={'fvar' in font}"
        )


if __name__ == "__main__":
    main()
