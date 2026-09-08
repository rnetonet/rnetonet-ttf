"""Build the `rnetonetcode` and `rnetonetmono` variable families by rebranding Cascadia.

Two families, four files, from the four upstream Cascadia variable fonts:

    rnetonet/sources/CascadiaCode.ttf        -> rnetonetcode-Roman.ttf
    rnetonet/sources/CascadiaCodeItalic.ttf  -> rnetonetcode-Italic.ttf
    rnetonet/sources/CascadiaMono.ttf        -> rnetonetmono-Roman.ttf
    rnetonet/sources/CascadiaMonoItalic.ttf  -> rnetonetmono-Italic.ttf

`rnetonetcode` is Cascadia Code (programming ligatures in `calt`); `rnetonetmono` is Cascadia
Mono (the same outlines with the ligature lookups removed -- upstream ships them as separate
files whose `glyf` and `cmap` are byte-identical and whose `calt` holds 116 lookups vs 1).

This is a **rebranding and default-settings pipeline**. Nothing is redrawn and nothing is
re-hinted: the outlines, the TrueType hinting (`fpgm`/`prep`/`cvt `/`cvar` and every glyph's
instruction stream) and the layout tables come from upstream untouched. Two things happen.

1. THE WEIGHT AXIS IS CUT DOWN TO TWO WEIGHTS AND RELABELLED.

   Upstream's `wght` runs 200-400-700 with six named instances. This family ships one step
   lighter, the same premise the JetBrains-based `rnetonet` had: Cascadia's Light is our
   Regular and Cascadia's SemiLight is our Bold.

       source wght 300 (Light)      -> output wght 400 (Regular)  -- also the new default
       source wght 350 (SemiLight)  -> output wght 700 (Bold)

   Step one is `instancer.instantiateVariableFont` with a *range* limit, `wght=(300, 300, 350)`.
   That keeps the font variable, restricts the axis to the 300-350 span, and moves the default
   onto 300 -- so `glyf` now holds the Light outlines, `cvt ` holds the Light control values
   rebased through `cvar`, and `gvar`/`HVAR`/`GDEF` carry only the deltas that reach from Light
   to SemiLight.

   Step two is the relabel: `fvar`'s user-space endpoints are rewritten from 300/300/350 to
   400/400/700. This is pure relabelling and cannot move an outline. Variation deltas live in
   *normalised* space (-1..1) and `avar` maps normalised to normalised; the only thing an
   `fvar` min/default/max triple decides is how a user-space number is projected onto that
   normalised range. Both triples project 300->0.0 and 350->1.0, so every rendered instance is
   identical -- `wght=400` renders exactly what `wght=300` did, `wght=700` exactly what 350 did,
   and `wght=550` the midpoint either way. `validate.py` proves this by instancing both fonts at
   matched positions and comparing every coordinate.

   Why relabel at all: the family has to *say* Regular and Bold. Left at 300-350 the OS reads a
   Light family -- `usWeightClass` 300, `font-weight: 400` resolving to the lighter end -- and
   every RIBBI convention in the OpenType stack argues with the file. Relabelled, `font-weight:
   400` is the Regular, `700` is the Bold, and the span between them stays continuously variable.

   The Regular/Bold contrast this buys is small on purpose: 1.2535x the ink (outline area over
   the 62 ASCII alphanumerics, source instanced at 350 vs 300). That is *more* contrast than the
   JetBrains-based family this replaces had at 1.1203, so the light-bold preference that family
   was tuned around survives the move.

2. THE METADATA IS REBRANDED. Family, subfamily, unique ID, full name, PostScript name and the
   variations PostScript prefix (nameID 25) are rewritten; `fvar` gets two named instances;
   `STAT` is rebuilt with a two-value `wght` axis and an `ital` axis; `OS/2` and `head` get the
   weight class and style bits that go with a Regular default.

What is NOT touched, and is checked table by table in `validate.py`: `glyf` outlines and
instruction streams (as the same slice of design space), `fpgm`, `prep`, `gasp`, `cmap`, `post`,
`GSUB` lookups, `GPOS`, vertical metrics (typo 1900/-480/0, win 2226/480, upem 2048 -- identical
across all four files, so line height is stable across both families), the monospace advance
(1200), and PANOSE. PANOSE weight stays at 6 (Medium) deliberately: it describes the weight the
font *declares*, which after the relabel is 400, not the master it was cut from.

Three things do change as a consequence of restricting the axis, each of them correct:

    cvt /cvar   `cvt ` is rebased onto the new default via `cvar`; `cvar` keeps only the
                Light->SemiLight deltas. The hinting *program* (`fpgm`/`prep`, and every glyph's
                bytecode) is byte-identical -- only the control values it reads move, which is
                exactly what a variable font's hinting is supposed to do at a new default.
    hmtx/hhea   advances stay 1200 everywhere; left side bearings follow the Light outlines, and
                `hhea`'s derived min/max fields follow the bearings.
    GSUB rvrn   dropped, with its 2 lookups. `rvrn` is upstream's required-variation feature and
                its condition sets cover normalised design 0.0-1.0, i.e. `wght` 400-700 in source
                terms. Our whole range sits at design -0.667..-0.333, below every condition, so
                the feature could never fire here. `calt`, `rclt`, `rlig`, the `ssXX` sets and
                every other feature come through with their lookups intact.

OFL compliance: Cascadia ships under an SIL OFL 1.1-based licence. Copyright (nameID 0), the
full licence (13) and licence URL (14) are preserved verbatim, as are the author/vendor
acknowledgements (8 "Saja Typeworks", 9 "Aaron Bell", 11/12) -- clause 4 permits exactly that.
The family is renamed, so clause 3 (Reserved Font Name) cannot bite whether or not Microsoft
reserved "Cascadia". The trademark line (nameID 7, "Cascadia Code is a trademark of the
Microsoft group of companies") is dropped, since these files are not Cascadia Code. No licence
text is altered (clause 5).

Filenames avoid the `Family[wght].ttf` convention on purpose: a literal `[wght]` in a filename
is a glob bracket expression and quietly breaks shell and Python globbing. `-Roman`/`-Italic`
mirrors upstream's own `CascadiaCodeRoman` variations prefix and globs cleanly.

Usage:
    python pipeline/build.py

Run `python pipeline/validate.py` afterwards to check the four outputs.
"""

import os

from fontTools.otlLib.builder import buildStatTable
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._f_v_a_r import NamedInstance
from fontTools.varLib import instancer

# Repo root, resolved from this file so the pipeline runs from any working directory.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND = "rnetonet"
SRC_DIR = os.path.join(REPO, BRAND, "sources")
OUT_DIR = os.path.join(REPO, BRAND)
WINDOWS = (3, 1, 0x409)

ITALIC, BOLD, REGULAR, USE_TYPO, WWS = 1 << 0, 1 << 5, 1 << 6, 1 << 7, 1 << 8
ELIDABLE = 0x2

# The cut. Source coordinates are Cascadia's named instances; output coordinates are the RIBBI
# weight classes they get relabelled to. Nothing between these two numbers is interpolated by us
# -- the span is upstream's own design space, just addressed under different user-space labels.
SRC_REGULAR, SRC_BOLD = 300, 350   # Cascadia Light, Cascadia SemiLight
OUT_REGULAR, OUT_BOLD = 400, 700   # our Regular, our Bold

# Names that describe Cascadia and must not survive the rename. 1-6 are rewritten; 7 is the
# Microsoft trademark line; 16/17 are the typographic family/subfamily, redundant once 1/2 are
# RIBBI-correct; 18/20/21/22 are legacy name slots that must not describe the old family; 25 is
# the variations PostScript prefix and is rewritten. Everything 256+ that the layout tables do
# not point at goes too -- upstream's are all `fvar`/`STAT` labels, which are rebuilt below.
DROP_IDS = {1, 2, 3, 4, 5, 6, 7, 16, 17, 18, 20, 21, 22, 25}

# Where a feature can hide a UI label in the 256+ range. Cascadia's `ssXX` sets currently carry
# none, but a source update could add them, and blanket-dropping 256+ would leave the feature UI
# nameless. Collect whatever the layout tables reference and keep exactly those.
FEATURE_NAME_ATTRS = (
    "UINameID",
    "FeatUILabelNameID",
    "FeatUITooltipTextNameID",
    "SampleTextNameID",
    "FirstParamUILabelNameID",
)

REGULAR_WGHT = dict(value=OUT_REGULAR, name="Regular", flags=ELIDABLE, linkedValue=OUT_BOLD)
BOLD_WGHT = dict(value=OUT_BOLD, name="Bold")
ROMAN_ITAL = dict(value=0, name="Roman", flags=ELIDABLE, linkedValue=1)
ITALIC_ITAL = dict(value=1, name="Italic")

# One entry per output file. `instances` is (subfamily label, PostScript suffix, output wght);
# the first is the default instance and reuses nameIDs 2 and 6 rather than minting new records,
# which is what the OpenType spec asks for and what readers expect to find there.
CUTS = [
    dict(suffix="Roman", subfamily="Regular", ps_suffix="Regular", italic=False,
         prefix="Roman", stat_ital=ROMAN_ITAL,
         instances=[("Regular", "Regular", OUT_REGULAR), ("Bold", "Bold", OUT_BOLD)]),
    dict(suffix="Italic", subfamily="Italic", ps_suffix="Italic", italic=True,
         prefix="Italic", stat_ital=ITALIC_ITAL,
         instances=[("Italic", "Italic", OUT_REGULAR), ("Bold Italic", "BoldItalic", OUT_BOLD)]),
]

# family -> (roman source, italic source)
FAMILIES = [
    ("rnetonetcode", "CascadiaCode.ttf", "CascadiaCodeItalic.ttf"),
    ("rnetonetmono", "CascadiaMono.ttf", "CascadiaMonoItalic.ttf"),
]


def referenced_name_ids(font):
    """nameIDs in the 256+ range that GSUB/GPOS feature parameters point at."""
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
    """`achVendID` as text. Vendor IDs are NUL-padded to four bytes and str.strip() does not
    remove NULs -- left alone they end up embedded in nameID 3."""
    return os2.achVendID.replace("\x00", "").strip()


def label(name, string):
    """The nameID of a 256+ record holding exactly `string`, adding one if there is none.

    `fvar` and `STAT` both need names for the axis and for each named position, and left to
    themselves they mint a fresh record every time -- so a file ends up with "Weight" twice and
    "Bold" twice. Interning them keeps one record per string."""
    for record in name.names:
        if record.nameID >= 256 and record.platformID == WINDOWS[0] and str(record) == string:
            return record.nameID
    return name.addName(string, platforms=(WINDOWS,))


def build(family, source, cut):
    src_path = os.path.join(SRC_DIR, source)
    # recalcTimestamp=False makes the build byte-reproducible. fontTools stamps `head.modified`
    # with the wall clock on save, which is the only thing that differed between two runs of this
    # script -- verified by diffing every table across two builds. Inheriting the source's
    # timestamp instead means the committed binaries can be re-derived and compared byte for byte
    # against the sources plus this file, which is the whole point of a rebranding pipeline.
    font = TTFont(src_path, recalcTimestamp=False)

    # Probe the layout tables before instancing, on the untouched source: whatever feature UI
    # labels exist upstream are what must survive the 256+ purge.
    keep = referenced_name_ids(font)

    # 1. Cut the axis down to Light..SemiLight and move the default onto Light.
    #
    # optimize=False turns off IUP delta re-optimization. That is not a performance choice: IUP
    # optimization drops deltas that interpolation can reproduce to within half a unit, and that
    # tolerance stacks on top of the rounding the default rebase already costs. Measured over
    # every point of every glyph, against the source pinned at the matching position:
    #     optimize=True   max 2 units off at the Bold end   595KB
    #     optimize=False  max 1 unit off anywhere           633KB
    # One unit (1/2048 em) is the floor, not a tunable: upstream did not draw Light on integer
    # coordinates -- it is an interpolation of Cascadia's masters -- so rebasing the default onto
    # it must round, and the Bold deltas then round against that rounded default. Paying 6% file
    # size to keep the whole axis at the floor is worth it for a pipeline whose promise is that
    # nothing was redrawn; a lossy re-encode is exactly the kind of thing it must not do.
    instancer.instantiateVariableFont(
        font, {"wght": (SRC_REGULAR, SRC_REGULAR, SRC_BOLD)}, inplace=True,
        optimize=False, updateFontNames=False,
    )

    name, os2, head, fvar = font["name"], font["OS/2"], font["head"], font["fvar"]

    # Read the source's version and vendor before the purge removes the records they live in.
    version = name.getDebugName(5) or "Version 1.000"
    id3 = name.getDebugName(3) or ""
    ver_num = (id3.split(";")[0] if id3.split(";")[0]
               else version.replace("Version ", "").split(";")[0].strip())
    ps_name = f"{family}-{cut['ps_suffix']}"
    vend = vendor_id(os2)

    drop = DROP_IDS | {i for i in range(256, 32768) if i not in keep}
    name.names = [r for r in name.names if r.nameID not in drop]
    for name_id, value in (
        (1, family),
        (2, cut["subfamily"]),
        (3, f"{ver_num};{vend};{ps_name}"),
        (4, f"{family} {cut['subfamily']}"),
        (5, version),
        (6, ps_name),
        # nameID 25 prefixes the PostScript name of any instance that has none of its own, so it
        # must be alphanumeric and must not collide with nameID 6 for a different style.
        (25, f"{family}{cut['prefix']}"),
    ):
        name.setName(value, name_id, *WINDOWS)

    # 2. Relabel the axis into RIBBI user space. Normalised space is untouched, so no outline
    #    moves -- see the module docstring.
    axis = next(a for a in fvar.axes if a.axisTag == "wght")
    assert (axis.minValue, axis.defaultValue, axis.maxValue) == (SRC_REGULAR, SRC_REGULAR, SRC_BOLD)
    axis.minValue, axis.defaultValue, axis.maxValue = OUT_REGULAR, OUT_REGULAR, OUT_BOLD
    axis.axisNameID = label(name, "Weight")

    fvar.instances = []
    for index, (style, ps_suffix, wght) in enumerate(cut["instances"]):
        instance = NamedInstance()
        instance.coordinates = {"wght": wght}
        if index == 0:                       # the default instance: reuse nameIDs 2 and 6
            instance.subfamilyNameID = 2
            instance.postscriptNameID = 6
        else:
            instance.subfamilyNameID = label(name, style)
            instance.postscriptNameID = label(name, f"{family}-{ps_suffix}")
        fvar.instances.append(instance)

    # 3. Style bits. The default instance is the Regular (or the Regular Italic), so no file is
    #    "bold" at its default -- Bold lives on the axis, not in these flags.
    os2.usWeightClass = OUT_REGULAR
    os2.fsSelection = (os2.fsSelection & ~(ITALIC | BOLD | REGULAR)) | USE_TYPO | WWS
    os2.fsSelection |= ITALIC if cut["italic"] else REGULAR
    head.macStyle = (head.macStyle & ~0b11) | (0b10 if cut["italic"] else 0)

    # buildStatTable accepts a nameID wherever it accepts a name string, so every label here
    # is interned first and STAT ends up pointing at the same records `fvar` does.
    def interned(value):
        return dict(value, name=label(name, value["name"]))

    buildStatTable(
        font,
        [
            dict(tag="wght", name=axis.axisNameID, ordering=0,
                 values=[interned(REGULAR_WGHT), interned(BOLD_WGHT)]),
            dict(tag="ital", name=label(name, "Italic"), ordering=1,
                 values=[interned(cut["stat_ital"])]),
        ],
        elidedFallbackName=label(name, "Regular"),
    )

    # buildStatTable adds Mac-platform records for its own names and the sources ship Mac copies
    # of everything; strip both so the name table stays Windows-only.
    name.names = [r for r in name.names if r.platformID != 1]

    if "DSIG" in font:                       # invalidated by any edit; instancer drops it already
        del font["DSIG"]

    out = f"{family}-{cut['suffix']}.ttf"
    font.save(os.path.join(OUT_DIR, out))
    print(
        f"{source:<26} -> {out:<26} "
        f"wght={axis.minValue:.0f}-{axis.defaultValue:.0f}-{axis.maxValue:.0f} "
        f"w={os2.usWeightClass} "
        f"inst={[name.getDebugName(i.subfamilyNameID) for i in fvar.instances]} "
        f"typo={'Y' if os2.fsSelection & USE_TYPO else 'n'} "
        f"win={os2.usWinAscent}/{os2.usWinDescent} upem={head.unitsPerEm} "
        f"names={len(name.names)} ui_labels={sorted(keep)}"
    )


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for family, roman_src, italic_src in FAMILIES:
        for source, cut in zip((roman_src, italic_src), CUTS):
            build(family, source, cut)


if __name__ == "__main__":
    main()
