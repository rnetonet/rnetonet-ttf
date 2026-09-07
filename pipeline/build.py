"""Build the `rnetonet` family by rebranding the JetBrains Mono static fonts.

`rnetonet` is a rebrand of **JetBrains Mono**, shifted one step lighter: JetBrains Mono's Light
ships as the family's Regular, and its Regular ships as the family's Bold.

    rnetonet/sources/JetBrainsMono-Light.ttf        (300) -> rnetonet-Regular.ttf        (-> 400)
    rnetonet/sources/JetBrainsMono-Regular.ttf      (400) -> rnetonet-Bold.ttf           (-> 700)
    rnetonet/sources/JetBrainsMono-LightItalic.ttf  (300) -> rnetonet-RegularItalic.ttf  (-> 400)
    rnetonet/sources/JetBrainsMono-Italic.ttf       (400) -> rnetonet-BoldItalic.ttf     (-> 700)

The sources are already static, so **nothing is instanced, interpolated or re-hinted** -- this is a
metadata rebrand and nothing more. Outlines (`glyf`/`loca`), hinting (`fpgm`/`prep`/`cvt `/`gasp`
and every per-glyph instruction stream), layout (`GSUB`/`GPOS`/`GDEF`), `cmap`, `hmtx` and `post`
are all passed through byte for byte; `validate.py` asserts exactly that. Only four tables change:

    name    rebranded (see below)
    OS/2    usWeightClass, fsSelection style bits
    head    macStyle style bits
    STAT    added -- the sources ship none, and a RIBBI family should declare its axis positions

JetBrains Mono is hinted with ttfautohint and already carries the smart-dropout instruction in
`prep`, so there is no dropout patch to apply and `head.flags` already has its integer-PPEM bit. Its
vertical metrics (typo 1020/-300/0, win 1020/300, upem 1000) are identical across all four faces
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

import os

from fontTools.otlLib.builder import buildStatTable
from fontTools.ttLib import TTFont

# Repo root, resolved from this file so the pipeline runs from any working directory.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAMILY = "rnetonet"
SRC_DIR = os.path.join(REPO, FAMILY, "sources")
OUT_DIR = os.path.join(REPO, FAMILY)
WINDOWS = (3, 1, 0x409)

ITALIC, BOLD, REGULAR, USE_TYPO, WWS = 1 << 0, 1 << 5, 1 << 6, 1 << 7, 1 << 8
ELIDABLE = 0x2

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
    # source, outfile, subfamily, ps suffix, weightclass, bold, italic, stat wght, stat ital
    ("JetBrainsMono-Light.ttf", "rnetonet-Regular.ttf", "Regular", "Regular",
     400, False, False, REGULAR_WGHT, ROMAN_ITAL),
    ("JetBrainsMono-Regular.ttf", "rnetonet-Bold.ttf", "Bold", "Bold",
     700, True, False, BOLD_WGHT, ROMAN_ITAL),
    ("JetBrainsMono-LightItalic.ttf", "rnetonet-RegularItalic.ttf", "Italic", "Italic",
     400, False, True, REGULAR_WGHT, ITALIC_ITAL),
    ("JetBrainsMono-Italic.ttf", "rnetonet-BoldItalic.ttf", "Bold Italic", "BoldItalic",
     700, True, True, BOLD_WGHT, ITALIC_ITAL),
]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    for src, out, subfamily, ps_suffix, weight_class, bold, italic, stat_w, stat_i in BUILDS:
        src_path = os.path.join(SRC_DIR, src)
        font = TTFont(src_path)
        name, os2, head = font["name"], font["OS/2"], font["head"]

        # Probe the layout tables on a throwaway handle. Reading GSUB through `font` would
        # decompile it, and fontTools would then recompile it on save -- semantically identical
        # but repacked, so the bytes would drift. Untouched tables stay untouched this way.
        keep = referenced_name_ids(TTFont(src_path, lazy=True))

        # Read source version/unique-id parts before the drop step removes them.
        version = name.getDebugName(5) or "Version 1.000"
        id3 = name.getDebugName(3) or ""
        ver_num = id3.split(";")[0] if id3.split(";")[0] else version.replace("Version ", "").split(";")[0].strip()
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
            f"names={len(name.names)} ss_labels={sorted(keep)}"
        )


if __name__ == "__main__":
    main()
