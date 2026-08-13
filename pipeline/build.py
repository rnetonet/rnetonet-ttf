"""Build the `rnetonet` family by instancing the Cascadia Code variable fonts.

`rnetonet` is a rebrand of **Cascadia Code** (the ligature-carrying cut of Cascadia, kept
intact). The four RIBBI styles are produced by pinning the `wght` axis of Cascadia Code's
variable fonts, so the whole family derives from two source files:

    rnetonet/sources/Cascadia_Code/CascadiaCode.ttf        @ wght=325 (Light..SemiLight) -> rnetonet-Regular.ttf        (-> 400)
    rnetonet/sources/Cascadia_Code/CascadiaCode.ttf        @ wght=350 (SemiLight)        -> rnetonet-Bold.ttf           (-> 700)
    rnetonet/sources/Cascadia_Code/CascadiaCodeItalic.ttf  @ wght=325 (Light..SemiLight) -> rnetonet-RegularItalic.ttf  (-> 400)
    rnetonet/sources/Cascadia_Code/CascadiaCodeItalic.ttf  @ wght=350 (SemiLight)        -> rnetonet-BoldItalic.ttf     (-> 700)

The Regular is pinned at wght 325 -- midway between Cascadia's Light (300) and SemiLight (350)
named instances (instancing accepts any axis value, not just named ones) -- and ships as the
family's Regular (usWeightClass 400); the SemiLight instance (wght 350) ships as its Bold (700).
That is a deliberately low-contrast pairing (only 25 axis units apart), so the four files still
form one RIBBI family that bold- and italic-links correctly.

Everything is one pass -- instancing, naming, STAT, vertical metrics, smart-dropout patch --
so no later step can orphan a name record. Glyph outlines, TrueType hinting (fpgm/prep/cvt/gasp)
and the layout tables (GSUB/GPOS, hence Cascadia Code's `calt`/`liga` ligatures) come straight
from the pinned instance untouched; only naming, weight/style flags, STAT and vertical metrics
are rewritten, plus a 7-byte smart-dropout instruction appended to `prep` (see below).

OFL compliance: copyright (nameID 0), full license (13), license URL (14) and author
acknowledgements (8/9) are preserved; the reserved name is dropped by renaming the family
(OFL clause 3) and the trademark line (7) is dropped. No license text is altered (clause 5).

Usage:
    python pipeline/build.py

Run `python pipeline/validate.py` afterwards to sanity-check the four outputs.
"""

import os

from fontTools.otlLib.builder import buildStatTable
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

# Repo root, resolved from this file so the pipeline runs from any working directory.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAMILY = "rnetonet"
SRC_DIR = os.path.join(REPO, FAMILY, "sources", "Cascadia_Code")
OUT_DIR = os.path.join(REPO, FAMILY)
WINDOWS = (3, 1, 0x409)

ITALIC, BOLD, REGULAR, USE_TYPO, WWS = 1 << 0, 1 << 5, 1 << 6, 1 << 7, 1 << 8
ELIDABLE = 0x2

# Cascadia Code's native vertical metrics (upem 2048), shared across every weight. Kept as the
# designer set them so line height is stable across the four styles.
WIN_ASCENT, WIN_DESCENT = 2226, 480

# Smart-dropout control: PUSHW[] 511; SCANCTRL[]; PUSHB[] 4; SCANTYPE[]. Cascadia's static builds
# carry this in `prep`; the variable fonts do not, so instancing would inherit its absence and
# fontbakery's `opentype/smart_dropout` would FAIL. We append it once (idempotent) so hinted
# rendering drops out thin stems the way the static builds do.
SMART_DROPOUT = bytes([0xB8, 0x01, 0xFF, 0x85, 0xB0, 0x04, 0x8D])

# Names that describe Cascadia Code and must not survive the rename. 1-6 are rewritten;
# 7 is the Microsoft trademark line; 16/17 are the typographic family/subfamily; 25 is the
# variations PostScript name prefix (dead once instanced).
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

ROMAN = "CascadiaCode.ttf"
ITAL = "CascadiaCodeItalic.ttf"

BUILDS = [
    # src, wght, outfile, subfamily, ps suffix, weightclass, bold, italic, stat wght, stat ital
    (ROMAN, 325, "rnetonet-Regular.ttf", "Regular", "Regular", 400, False, False, REGULAR_WGHT, ROMAN_ITAL),
    (ROMAN, 350, "rnetonet-Bold.ttf", "Bold", "Bold", 700, True, False, BOLD_WGHT, ROMAN_ITAL),
    (ITAL, 325, "rnetonet-RegularItalic.ttf", "Italic", "Italic", 400, False, True, REGULAR_WGHT, ITALIC_ITAL),
    (ITAL, 350, "rnetonet-BoldItalic.ttf", "Bold Italic", "BoldItalic", 700, True, True, BOLD_WGHT, ITALIC_ITAL),
]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    for src, wght, out, subfamily, ps_suffix, weight_class, bold, italic, stat_w, stat_i in BUILDS:
        font = instancer.instantiateVariableFont(
            TTFont(os.path.join(SRC_DIR, src)), {"wght": wght}, inplace=True, updateFontNames=False
        )
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
        # TrueType-hinted (fpgm/prep/cvt) -> PPEM must round to integers: keep head.flags bit 3
        # (Cascadia already sets it; kept explicit and idempotent).
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

        font.save(os.path.join(OUT_DIR, out))
        prep_len = len(font["prep"].program.getBytecode()) if "prep" in font else 0
        print(
            f"{src:<24} @wght={wght} -> {out:<28} w={weight_class} "
            f"typo={'Y' if os2.fsSelection & USE_TYPO else 'n'} "
            f"win={os2.usWinAscent}/{os2.usWinDescent} names={len(name.names)} "
            f"prep={prep_len} fvar={'fvar' in font}"
        )


if __name__ == "__main__":
    main()
