"""Build the `rnetonet` family by rebranding the JetBrains Mono static fonts.

`rnetonet` is a rebrand of **JetBrains Mono**, shifted one step lighter: JetBrains Mono's Light
ships as the family's Regular, and its Regular ships as the family's Bold.

    rnetonet/sources/JetBrainsMono-Light.ttf        (300) -> rnetonet-Regular.ttf        (-> 400)
    rnetonet/sources/JetBrainsMono-Regular.ttf      (400) -> rnetonet-Bold.ttf           (-> 700)
    rnetonet/sources/JetBrainsMono-LightItalic.ttf  (300) -> rnetonet-RegularItalic.ttf  (-> 400)
    rnetonet/sources/JetBrainsMono-Italic.ttf       (400) -> rnetonet-BoldItalic.ttf     (-> 700)

The sources are already static, so **nothing is instanced or interpolated and no outline is ever
redrawn**. Two things happen: the fonts are re-hinted -- at stock ttfautohint settings but with a
latin fallback script, so the symbol glyphs get hinted too -- and the metadata is rebranded.

Glyph *outlines* come through untouched -- `validate.py` compares every point coordinate against
the source -- as do the layout tables that carry the ligatures and stylistic sets
(`GSUB`/`GPOS`/`GDEF`), plus `cmap`, `hmtx`, `hhea`, `post` and `gasp`. What changes:

    fpgm/prep/cvt   re-hinted; `cvt ` gains entries from the control instruction (see HINT_OPTIONS)
    glyf            re-hinted -- instruction streams only; coordinates are identical
    TTFA            added by ttfautohint -- records every parameter used, so the hinting is auditable
    name            rebranded, plus the ttfautohint version stamp in nameID 5
    OS/2            usWeightClass, fsSelection style bits
    head            macStyle style bits
    STAT            added -- the sources ship none, and a RIBBI family should declare its axis positions

Upstream JetBrains Mono 2.304 is hinted with **stock ttfautohint defaults** -- verified, not
assumed: re-running ttfautohint with no options reproduces its `fpgm`, `prep`, `cvt ` and `glyf`
byte for byte, even though the ttfautohint here (1.8.4.16-eb64) is a newer build than the one
upstream used (1.8.4.7-5d5b). One default is wrong for a coding font -- `fallback-script=none`
leaves every box-drawing and block glyph unhinted -- so that is the single parameter this build
changes on its own. The second departure is a control instruction, `* dflt width 74`, which nudges
the standard stem width three units above the 71 ttfautohint measures from the outlines -- a
preference, not a fix, argued out in HINT_OPTIONS below. Both
stem width modes have been moved and moved back; HINT_OPTIONS below records why, and documents the
one dial that is actually fine-grained. The smart-dropout instruction and the integer-PPEM
`head.flags` bit survive re-hinting, so there is still no dropout patch to apply.

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
from ttfautohint import ttfautohint

# Repo root, resolved from this file so the pipeline runs from any working directory.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAMILY = "rnetonet"
SRC_DIR = os.path.join(REPO, FAMILY, "sources")
OUT_DIR = os.path.join(REPO, FAMILY)
WINDOWS = (3, 1, 0x409)

ITALIC, BOLD, REGULAR, USE_TYPO, WWS = 1 << 0, 1 << 5, 1 << 6, 1 << 7, 1 << 8
ELIDABLE = 0x2

# ttfautohint parameters. Upstream ships stock defaults; the one departure is the fallback script,
# plus the info table. Everything else stays at its default -- twice on purpose now, see below.
#
#   fallback_script="latn"
#       The default, "none", means any glyph outside a recognised script gets no hinting at all --
#       and in this font that is 128 box-drawing glyphs, 32 block elements, 21 arrows, 62 math
#       symbols and 43 geometric shapes. Exactly the glyphs a terminal draws TUI borders, tables,
#       tree views and progress bars with. Hinting them against latin blue zones snaps their rules
#       onto the pixel grid instead of smearing them across two rows. It touches *only* those
#       glyphs: everything with a real script is hinted identically to upstream. Verified glyph by
#       glyph rather than assumed -- 1215 of 1743 instruction streams come through byte for byte,
#       and the 528 that change are box drawing (128), technical (105), math (105), other symbols
#       (48), arrows (34), blocks (32), geometric (28), plus the letterlike math alphanumerics
#       (double-struck CHNPQRZ, script l), 12 math brackets/ceilings/floors, one Gujarati digit and
#       8 unencoded glyphs. No Latin letter, digit or ASCII punctuation mark moves.
#
#   *_stem_width_mode
#       Left at ttfautohint's defaults: QUANTIZED for grayscale and DirectWrite ClearType, STRONG
#       for GDI ClearType. Both non-GDI ones have now been moved and moved back, in both
#       directions, and that pair of results is the useful part:
#           STRONG   (34aed65, reverted in 5bbd30c) +32% fully-saturated ink on letters and digits.
#                    Measured well; read brittle in daily use.
#           NATURAL  (ed31a38, reverted here) -1.7%. Too small to notice in daily use, which is the
#                    finding: the mode switch has nothing useful in its soft half.
#       So the mode is a coarse switch -- one step too hard, one step indistinguishable -- and both
#       ends are now spent. Since all three sit at their defaults, none is passed: an unset option
#       is the honest way to say "stock", and TTFA records the effective values regardless.
#       ttfautohint emits a `prep` that branches on rendering mode, and it is easy to get backwards
#       which branch reaches whom:
#           dw_cleartype  -> FreeType's default v40 interpreter, and DirectWrite. v40 emulates
#                            ClearType, so this is the one nearly every modern reader gets.
#           gray          -> only the legacy v35 interpreter (grayscale, full hinting).
#           gdi_cleartype -> only Windows GDI ClearType.
#
#   TTFA_info=True
#       Writes a TTFA table listing every parameter used, so a built font says how it was hinted.
#       Upstream ships no such table; this is an audit aid, not a hinting parameter, and it is what
#       validate.py reads to prove the configuration has not drifted.
#
# Re-hinting is a no-op on the hinting tables. Running this ttfautohint (1.8.4.16-eb64, a newer
# build than the 1.8.4.7-5d5b stamped into the sources) with stock parameters reproduces upstream's
# fpgm, prep, cvt and glyf byte for byte, on both roman faces. Only fallback_script=latn changes
# anything at all, and only for the 286 symbol glyphs.
#
# Measured on the Light face, as the fraction of ink rendered at full saturation rather than smeared
# into half-grays, over 9-18 ppem under FreeType's default v40 interpreter (so, the dw branch):
#                                   symbols   letters+digits   Bold/Regular ink ratio
#   upstream defaults                0.2962       0.0800               1.1203
#   fallback_script=latn (ours)      0.3041       0.0800               1.1203
#   + gray/dw NATURAL (reverted)     0.2978       0.0786               1.1236
#   + gray/dw STRONG (reverted)      0.3819       0.1059               1.0938
# So this build buys +2.7% on symbols and leaves letters, digits and weight contrast exactly where
# upstream has them.
#
#   control_buffer="* dflt width 74\n"
#       The shipped nudge, and the only setting here that is a preference rather than a fix. See
#       THE FINE DIAL below for what it buys, what it costs, and the case against it.
#
# THE FINE DIAL. The stem width *mode* is coarse, but the standard stem width itself is a number,
# and control instructions can set it:
#
#     control_buffer="* dflt width N\n"        (N in font units)
#
# ttfautohint auto-detects 71 for JetBrains Mono Light -- verified, not guessed: `width 71` renders
# identically to leaving it auto (same glyf bytes, same measurements to four decimals). Measured on
# letters and digits, 9-18 ppem, against that baseline:
#       66-69     -12% crisp, -1.5% ink        a cliff, not a nudge
#       70        -3.9% crisp, -0.3% ink       a little softer
#       71        auto -- what ttfautohint measures from the outlines
#       74        +2.1% crisp, +0.9% ink       SHIPPED -- the smallest perceptible step up
#       75-77     +1.9 to +2.7% crisp, +1.3 to +1.9% ink
#       78-80     +3.7 to +4.0% crisp, +2.5% ink
#       90+       +14% and up -- back in STRONG territory
# Two caveats. It is steppy rather than smooth: quantized mode snaps to a set of widths, so 72 and
# 73 measure slightly *below* 71 rather than above. And it moves weight as well as crispness --
# roughly +0.3% ink per unit -- so it doubles as a weight trim, which on a Light-based family is
# not nothing. `latn dflt width N` is NOT a way to spare the symbols, which is the
# obvious guess and wrong: fallback_script is latn, so the symbol glyphs are hinted *as*
# latin and take the same width. Measured identical to `* dflt` on letters and symbols
# alike; at width 76, 15 box-drawing glyphs change under either form.
#
# The case against shipping any width, recorded because it was argued and overruled rather than
# missed: 71 is not a default, it is a *measurement of this typeface* -- ttfautohint derives it from
# the stems of the standard characters as drawn. Overriding it to 74 tells the hinter the stems are
# thicker than they are, and the +0.9% ink says the rest: at 13-17ppem the font renders slightly
# heavier than JetBrains Mono Light actually is. On a family whose entire premise is being one step
# light (JB Light as Regular), that partly argues with itself, and the honest lever for weight is
# the source weight rather than the hint. 74 was chosen anyway, deliberately, as the smallest step
# that reads: +0.9% ink is close to nothing, and the alternative was shipping a font its owner finds
# a shade soft. 78-80 were rejected on exactly this ground -- there the weight gain is visible.
#
# It also costs a guarantee. Control instructions add `cvt ` entries, so `cvt ` is no longer
# byte-identical to the source and has moved out of validate.py's PRESERVED set into the re-hinted
# one. That is a deliberate, recorded widening of the build's scope, not a silenced check.
#
# Rejected after measuring -- recorded so none of it gets retried on a hunch:
#   x_height_snapping_exceptions="-"   -5.5% crisp and -3.7% ink, the largest move still available
#                            while staying hinted; built as a side-by-side family and read in situ.
#                            No real improvement, and it costs a pixel of x-height at 13/15/17ppem.
#   increase_x_height        a threshold, not a dial: 0/10/12 all measure -6.0%, 18/24/32 all
#                            measure identical to the default 14. Nothing usable in between.
#   hinting_range_min=14     a no-op; below range-min ttfautohint reuses the smallest hint set.
#   hinting_limit=N          not a dial but a cliff -- hinting stops entirely above N ppem.
#   hint_composites          identical metrics even on composite glyphs (accented letters, and the
#                            27 composite ligature glyphs), and +53KB a face. Composites inherit
#                            their components' hinting, which is already correct.
#   adjust_subglyphs         accent separation fell 0.865 -> 0.816, and +95KB a face.
#   windows_compatibility    identical metrics, and it would rewrite the usWin metrics the family
#                            deliberately keeps as shipped.
#   hinting_range_max=72     identical even measured at 52-72ppem, where alone it could matter.
#   --reference              the faces already agree on x-height, cap-height and baseline at every
#                            ppem from 9 to 24, so sharing blue zones would change nothing.
#   fallback_scaling         actively harmful: accent separation collapsed 0.86 -> 0.16.
HINT_OPTIONS = dict(
    fallback_script="latn",
    control_buffer="* dflt width 74\n",
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
