"""Build the `rnetonet` family by rebranding the JetBrains Mono static fonts.

`rnetonet` is a rebrand of **JetBrains Mono**, shifted one step lighter: JetBrains Mono's Light
ships as the family's Regular, and its Regular ships as the family's Bold.

    rnetonet/sources/JetBrainsMono-Light.ttf        (300) -> rnetonet-Regular.ttf        (-> 400)
    rnetonet/sources/JetBrainsMono-Regular.ttf      (400) -> rnetonet-Bold.ttf           (-> 700)
    rnetonet/sources/JetBrainsMono-LightItalic.ttf  (300) -> rnetonet-RegularItalic.ttf  (-> 400)
    rnetonet/sources/JetBrainsMono-Italic.ttf       (400) -> rnetonet-BoldItalic.ttf     (-> 700)

The sources are already static, so **nothing is instanced or interpolated and no outline is ever
redrawn**. Two things happen: the fonts are re-hinted -- close to stock ttfautohint settings, with
a latin fallback script so the symbol glyphs get hinted too and the softest stem width mode so the
letters do not read brittle -- and the metadata is rebranded.

Glyph *outlines* come through untouched -- `validate.py` compares every point coordinate against
the source -- as do the layout tables that carry the ligatures and stylistic sets
(`GSUB`/`GPOS`/`GDEF`), plus `cmap`, `hmtx`, `hhea`, `post`, `cvt ` and `gasp`. What changes:

    fpgm/prep/glyf  re-hinted (instruction streams only; coordinates are identical)
    TTFA            added by ttfautohint -- records every parameter used, so the hinting is auditable
    name            rebranded, plus the ttfautohint version stamp in nameID 5
    OS/2            usWeightClass, fsSelection style bits
    head            macStyle style bits
    STAT            added -- the sources ship none, and a RIBBI family should declare its axis positions

Upstream JetBrains Mono 2.304 is hinted with **stock ttfautohint defaults** -- verified, not
assumed: re-running ttfautohint with no options reproduces its `fpgm`, `prep`, `cvt ` and `glyf`
byte for byte. Two of those defaults are changed here. `fallback-script=none` is simply wrong for a
coding font: it leaves every box-drawing and block glyph unhinted. And the stem width modes are
moved from QUANTIZED to NATURAL, the softest setting ttfautohint has, because this family is read
all day and quantized stems came out harder-edged than wanted -- see HINT_OPTIONS below, which
records what that costs, what the STRONG experiment cost before it, and how small the move actually
measures. The smart-dropout instruction and the integer-PPEM `head.flags` bit survive re-hinting,
so there is still no dropout patch to apply.

Vertical metrics (typo 1020/-300/0, win 1020/300, upem 1000) are identical across all four faces
and are kept exactly as shipped, so line height is stable across the family.

JetBrains Mono's coding ligatures are carried over untouched: they live in `calt`, which stays as
shipped, so `-> => != ===` still render as ligatures. The `cvXX` character variants and `ssXX`
stylistic sets survive too, including the UI name labels `GSUB` points at (nameIDs 256-259:
"Classic construction", "Closed construction", "Broken equals ligatures", "Rased bar f") -- those
are found by walking the layout tables rather than being hardcoded.

OFL compliance: copyright (nameID 0), full license (13), license URL (14) and author
acknowledgements (8/9, plus vendor/designer URLs 11/12) are preserved; the family is renamed
(JetBrains Mono carries no Reserved Font Name, so clause 3 does not bite, but the rename makes the
derivative unmistakable) and the trademark line (7) is dropped since the result is not JetBrains
Mono. No license text is altered (clause 5).

Usage:
    python pipeline/build.py

Run `python pipeline/validate.py` afterwards to sanity-check the four outputs.
"""

import io
import os

from fontTools.otlLib.builder import buildStatTable
from fontTools.ttLib import TTFont
from ttfautohint import StemWidthMode, ttfautohint

# Repo root, resolved from this file so the pipeline runs from any working directory.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAMILY = "rnetonet"
SRC_DIR = os.path.join(REPO, FAMILY, "sources")
OUT_DIR = os.path.join(REPO, FAMILY)
WINDOWS = (3, 1, 0x409)

ITALIC, BOLD, REGULAR, USE_TYPO, WWS = 1 << 0, 1 << 5, 1 << 6, 1 << 7, 1 << 8
ELIDABLE = 0x2

# ttfautohint parameters. Upstream ships stock defaults; two of them depart here -- the fallback
# script and the stem width modes -- plus the info table. Everything else stays at its default,
# deliberately.
#
#   fallback_script="latn"
#       The default, "none", means any glyph outside a recognised script gets no hinting at all --
#       and in this font that is 128 box-drawing glyphs, 32 block elements, 21 arrows, 62 math
#       symbols and 43 geometric shapes. Exactly the glyphs a terminal draws TUI borders, tables,
#       tree views and progress bars with. Hinting them against latin blue zones snaps their rules
#       onto the pixel grid instead of smearing them across two rows. It touches *only* those
#       glyphs: everything with a recognised script is left to the stem width modes below.
#
#   gray_stem_width_mode = dw_cleartype_stem_width_mode = NATURAL
#       The softness dial, turned down one step past upstream. The three modes differ only in how
#       far a stem width is allowed to be pulled towards the pixel grid:
#           NATURAL    (ours) no rounding at all -- a stem keeps its fractional width, so its edge
#                      keeps its partial coverage instead of being pulled onto a step. Softest.
#           QUANTIZED  (ttfautohint's default, and what upstream JetBrains Mono ships) rounds stem
#                      widths onto a quantized set.
#           STRONG     snaps stems onto whole pixels. Set in commit 34aed65 and reverted in
#                      5bbd30c: it measured much crisper and read brittle in daily use.
#       ttfautohint emits a `prep` that branches on rendering mode, and it is easy to get backwards
#       which branch reaches whom:
#           dw_cleartype  -> FreeType's default v40 interpreter, and DirectWrite. v40 emulates
#                            ClearType, so this is the one nearly every modern reader gets.
#           gray          -> only the legacy v35 interpreter (grayscale, full hinting).
#           gdi_cleartype -> only Windows GDI ClearType. Left at its STRONG default: nothing in
#                            this pipeline can render that branch, so softening it would be a
#                            change made blind, and upstream ships it as it is.
#
#   TTFA_info=True
#       Writes a TTFA table listing every parameter used, so a built font says how it was hinted.
#
# Measured on the Light face, as the fraction of ink rendered at full saturation rather than smeared
# into half-grays, over 9-18 ppem under FreeType's default v40 interpreter (so, the dw branch):
#                                   symbols   letters+digits   Bold/Regular ink ratio
#   upstream defaults                0.2962       0.0800               1.1203
#   + fallback_script=latn           0.3041       0.0800               1.1203
#   + gray/dw NATURAL (ours)         0.2978       0.0786               1.1236
#   + gray/dw STRONG (reverted)      0.3819       0.1059               1.0938
#
# Read those honestly. NATURAL is a *small* move: -1.7% on letters and digits, -2.1% on symbols,
# against the +32% that STRONG added. Stem width mode is the only softness flag ttfautohint offers
# and this is its softest setting, so a font that still reads too crisp is not going to be fixed by
# another flag -- the remaining levers are `hinting_limit` (stop hinting above a ppem) or dropping
# hinting altogether, both of which give up the symbol hinting this build exists for.
# What NATURAL does buy outright is weight separation: the Bold/Regular ink ratio goes from 1.1203
# to 1.1236, which matters here because this family's Bold is only one step above its Regular
# (JetBrains Light 300 vs Regular 400).
#
# These numbers were re-measured for this change. The harness that produced the figures quoted in
# commits 34aed65 and 5bbd30c was never committed, so absolute values differ from those; the
# ordering of the rows and the direction of every delta agree. The metric is a proxy for crispness
# -- it is not legibility, and only FreeType grayscale can be driven from here.
#
# Rejected after measuring -- recorded so none of it gets retried on a hunch:
#   hint_composites          identical metrics even on composite glyphs (accented letters, and the
#                            27 composite ligature glyphs), and +53KB a face. Composites inherit
#                            their components' hinting, which is already correct.
#   adjust_subglyphs         accent separation fell 0.865 -> 0.816, and +95KB a face.
#   x_height_snapping_exceptions="6-16"   +1% crispness, but accent separation fell to 0.812.
#   windows_compatibility    identical metrics, and it would rewrite the usWin metrics the family
#                            deliberately keeps as shipped.
#   increase_x_height        0/12/16/18 all no gain.
#   hinting_range_max=72     identical even measured at 52-72ppem, where alone it could matter.
#   --reference              the faces already agree on x-height, cap-height and baseline at every
#                            ppem from 9 to 24, so sharing blue zones would change nothing.
#   fallback_scaling         actively harmful: accent separation collapsed 0.86 -> 0.16.
HINT_OPTIONS = dict(
    fallback_script="latn",
    gray_stem_width_mode=StemWidthMode.NATURAL,
    dw_cleartype_stem_width_mode=StemWidthMode.NATURAL,
    TTFA_info=True,
)

# Names that describe JetBrains Mono and must not survive the rename. 1-6 are rewritten; 7 is the
# JetBrains trademark line; 16/17 are the typographic family/subfamily, which the Light faces carry
# and which become redundant once 1/2 are RIBBI-correct; 18/20/21/22/25 are legacy/variable-font
# name slots that must not describe the old family if present.
DROP_IDS = {1, 2, 3, 4, 5, 6, 7, 16, 17, 18, 20, 21, 22, 25}

# IDs 256+ hold the stylistic-set UI labels that GSUB points at. Dropping the whole range would
# orphan them and the feature UI would go nameless, so collect what the layout tables reference and
# keep exactly those.
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


def vendor_id(os2):
    """`achVendID` as text. JetBrains pads theirs to four bytes with NULs ('JB\\0\\0'), and
    str.strip() does not remove those -- left alone they end up embedded in nameID 3."""
    return os2.achVendID.replace("\x00", "").strip()


REGULAR_WGHT = dict(value=400, name="Regular", flags=ELIDABLE, linkedValue=700)
BOLD_WGHT = dict(value=700, name="Bold")
ROMAN_ITAL = dict(value=0, name="Roman", flags=ELIDABLE, linkedValue=1)
ITALIC_ITAL = dict(value=1, name="Italic")

BUILDS = [
    # The filename suffix and the PostScript suffix are deliberately not the same for the roman
    # italic: the file is named for its role in the family (RegularItalic), while the PostScript
    # name follows the RIBBI convention (Italic).
    # source, subfamily, file suffix, ps suffix, weightclass, bold, italic, stat wght, stat ital
    ("JetBrainsMono-Light.ttf", "Regular", "Regular", "Regular",
     400, False, False, REGULAR_WGHT, ROMAN_ITAL),
    ("JetBrainsMono-Regular.ttf", "Bold", "Bold", "Bold",
     700, True, False, BOLD_WGHT, ROMAN_ITAL),
    ("JetBrainsMono-LightItalic.ttf", "Italic", "RegularItalic", "Italic",
     400, False, True, REGULAR_WGHT, ITALIC_ITAL),
    ("JetBrainsMono-Italic.ttf", "Bold Italic", "BoldItalic", "BoldItalic",
     700, True, True, BOLD_WGHT, ITALIC_ITAL),
]



def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    for (src, subfamily, file_suffix, ps_suffix, weight_class, bold, italic,
         stat_w, stat_i) in BUILDS:
        src_path = os.path.join(SRC_DIR, src)

        # Re-hint first, then rebrand the result -- so the name table we write is the final word
        # and ttfautohint cannot stamp over it.
        with open(src_path, "rb") as handle:
            hinted = ttfautohint(in_buffer=handle.read(), **HINT_OPTIONS)

        # Probe the layout tables on a throwaway handle. Reading GSUB through the font we save
        # would decompile it, and fontTools would then recompile it on save -- semantically
        # identical but repacked, so the bytes would drift. Untouched tables stay untouched.
        keep = referenced_name_ids(TTFont(src_path, lazy=True))

        out = f"{FAMILY}-{file_suffix}.ttf"
        font = TTFont(io.BytesIO(hinted))
        name, os2, head = font["name"], font["OS/2"], font["head"]

        # Read source version/unique-id parts before the drop step removes them.
        version = name.getDebugName(5) or "Version 1.000"
        id3 = name.getDebugName(3) or ""
        ver_num = (id3.split(";")[0] if id3.split(";")[0]
                   else version.replace("Version ", "").split(";")[0].strip())
        ps_name = f"{FAMILY}-{ps_suffix}"
        vend = vendor_id(os2)

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
        os2.fsSelection = (os2.fsSelection & ~(ITALIC | BOLD | REGULAR)) | USE_TYPO | WWS
        os2.fsSelection |= (BOLD if bold else 0) | (ITALIC if italic else 0)
        if not bold and not italic:
            os2.fsSelection |= REGULAR

        head.macStyle = (head.macStyle & ~0b11) | (0b1 if bold else 0) | (0b10 if italic else 0)

        buildStatTable(
            font,
            [
                dict(tag="wght", name="Weight", ordering=0, values=[stat_w]),
                dict(tag="ital", name="Italic", ordering=1, values=[stat_i]),
            ],
            elidedFallbackName="Regular",
        )

        # buildStatTable adds Mac-platform records for its own names, and the sources ship Mac
        # copies of the stylistic-set labels; strip both so the name table stays Windows-only.
        name.names = [r for r in name.names if r.platformID != 1]

        if "DSIG" in font:
            del font["DSIG"]

        font.save(os.path.join(OUT_DIR, out))
        print(
            f"{src:<30} -> {out:<28} w={weight_class} "
            f"typo={'Y' if os2.fsSelection & USE_TYPO else 'n'} "
            f"win={os2.usWinAscent}/{os2.usWinDescent} upem={head.unitsPerEm} "
            f"names={len(name.names)} ss_labels={sorted(keep)} TTFA={'TTFA' in font}"
        )


if __name__ == "__main__":
    main()
