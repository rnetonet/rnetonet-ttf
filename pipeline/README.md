# rnetonet build pipeline

Two scripts that reproduce and verify the `rnetonet` variable font family from its upstream
source. It is a rebrand of **Cascadia Mono**, shifted lighter: Regular sits exactly halfway
between Cascadia's Light and its SemiLight, and Bold is SemiLight itself.

Nothing is redrawn and nothing is re-hinted. The build cuts Cascadia's weight axis down to that
span, relabels it 400–700 so the OS reads a Regular and a Bold, and rebrands the metadata.
`validate.py` proves the scope by instancing source and output at matching positions and comparing
every glyph coordinate and every GPOS value, by re-shaping a text corpus through both with
HarfBuzz, and by diffing every table the build has no business touching.

```
rnetonet/
  sources/                       <- upstream Cascadia Mono 2407.024 (build inputs)
    CascadiaMono.ttf                   wght 200-400-700, roman
    CascadiaMonoItalic.ttf             wght 200-400-700, italic
  rnetonet-Roman.ttf             <- build outputs (committed)
  rnetonet-Italic.ttf
pipeline/
  build.py
  validate.py
```

Cascadia Mono is Cascadia Code without the programming ligatures — upstream ships them as separate
files whose `glyf` and `cmap` are byte-identical, differing only in `calt`, which carries 116
lookups in Code and 1 in Mono. Mono is the deliberate choice: `->`, `!=` and `===` stay as the
characters they are, and `validate.py` asserts it behaviourally.

Filenames deliberately avoid the `Family[wght].ttf` convention: a literal `[wght]` is a glob
bracket expression and quietly breaks shell and Python globbing. `-Roman`/`-Italic` mirrors
upstream's own `CascadiaMonoRoman` variations prefix and globs cleanly.

## Run

```sh
python pipeline/build.py       # cut + relabel + rebrand -> rnetonet/rnetonet-{Roman,Italic}.ttf
python pipeline/validate.py    # OTS + build-scope + shaping + structural + fontbakery gate
```

Both scripts resolve the repo root from their own location, so they run from any working
directory. They only write `rnetonet/`; sources are read, never modified.

The build is **byte-reproducible**: two runs produce identical files. `head.modified` was the only
thing that differed before `build.py` started passing `recalcTimestamp=False`, so the committed
binaries can be re-derived and compared byte for byte against the sources plus the script.

## What `build.py` does

| Source | wght in | Output | wght out | size |
|---|---|---|---|---|
| `CascadiaMono.ttf`       | 200‑400‑700 | `rnetonet-Roman.ttf`  | 400‑400‑700 | 587 KB, 4319 glyphs |
| `CascadiaMonoItalic.ttf` | 200‑400‑700 | `rnetonet-Italic.ttf` | 400‑400‑700 | 428 KB, 3076 glyphs |

Two named instances per file, and no more:

| Output instance | wght | is upstream's |
|---|---|---|
| Regular / Italic   | 400 | 325 — exactly midway between Light (300) and SemiLight (350) |
| Bold / Bold Italic | 700 | SemiLight (350) |

### 1. The cut

`instancer.instantiateVariableFont(font, {"wght": (325, 325, 350)})` keeps the font variable,
restricts the axis to the 325–350 span, and moves the default onto 325. `glyf` then holds the
midpoint outlines, `cvt ` holds the midpoint control values rebased through `cvar`, and
`gvar`/`HVAR`/`GDEF` carry only the deltas that reach from there to SemiLight.

325 is a true midpoint in both senses, which is what makes it spellable at all: upstream's `avar`
runs straight from normalised −0.5 (Light) to −0.25 (SemiLight), so user-space 325 lands on design
coordinate −0.50000, exactly between Light's −0.66669 and SemiLight's −0.33331. Regular is
therefore an interpolation rather than one of upstream's named instances; Bold is SemiLight
exactly.

`optimize=False` turns off IUP delta re-optimization. That is a correctness choice, not a speed
one: IUP optimization drops deltas that interpolation can reproduce to within half a unit, and
that tolerance stacks on the rounding the default rebase already costs. One unit (1/2048 em) is a
floor, not a tunable — the Regular is an interpolation, so it is not on integer coordinates, and
rebasing the default onto it must round; the Bold deltas then round against that rounded default.
Paying ~6% file size to keep the whole axis at that floor is worth it in a pipeline whose promise
is that nothing was redrawn.

### 2. The relabel

`fvar`'s user-space endpoints are rewritten from 325/325/350 to 400/400/700. This is pure
relabelling and cannot move an outline: variation deltas live in *normalised* space (−1..1) and
`avar` maps normalised to normalised, so the only thing an `fvar` min/default/max triple decides
is how a user-space number is projected onto that normalised range. Both triples project
325 → 0.0 and 350 → 1.0, so `wght=400` renders exactly what `wght=325` did, `wght=700` exactly
what 350 did, and `wght=550` the midpoint either way.

The relabel stays affine because the whole cut, normalised −0.375 to −0.25, sits inside that one
straight `avar` segment. `validate.py` re-derives the span from the source and checks the middle of
the axis as well as the ends, so a source whose `avar` grew a knee in here would fail rather than
quietly bend.

**Why relabel at all.** The family has to *say* Regular and Bold. Left at 325–350, the OS reads a
Light family: `usWeightClass` 325, `font-weight: 400` resolving to the lighter end, and every RIBBI
convention in the OpenType stack arguing with the file. Relabelled, `font-weight: 400` is the
Regular, `700` is the Bold, and everything between stays continuously variable.

### 3. The contrast this buys

Bold carries **1.1124×** the ink of Regular in the roman and **1.1104×** in the italic — outline
area over the 62 ASCII alphanumerics, measured on the built fonts at wght 700 against 400. For
reference, across upstream's own axis measured against Light:

| upstream instance | ink vs Light |
|---|---|
| ExtraLight 200 | 0.74× |
| Light 300 | 1.00× |
| **325** (our Regular) | **1.13×** |
| **SemiLight 350** (our Bold) | **1.25×** |
| Regular 400 | 1.50× |
| SemiBold 600 | 1.74× |
| Bold 700 | 1.89× |

That is a deliberately light bold, close to the 1.1203× the JetBrains-based `rnetonet` shipped
before it. Anchoring Regular at the midpoint rather than at Light is what buys that while keeping
Bold on a real upstream master.

### 4. The rebrand

Family, subfamily, unique ID, full name, PostScript name and the variations PostScript prefix
(nameID 25) are rewritten; `fvar` gets its two named instances, the default one reusing nameIDs 2
and 6 rather than minting new records; `STAT` is rebuilt with a two-value `wght` axis (Regular
elided and linked to Bold) and an `ital` axis; `OS/2` and `head` get the weight class and style
bits that go with a Regular default — neither file is "bold" at its default, because Bold lives on
the axis.

Name records for `fvar` and `STAT` are interned, so a file carries one "Weight" and one "Bold"
record rather than the duplicates each builder would otherwise mint.

## What is preserved, and what necessarily moves

Untouched, and checked table by table:

`glyf` outlines and instruction streams · `fpgm` · `prep` · `gasp` · `cmap` · `post` ·
`GSUB` lookups · vertical metrics (typo 1900/−480/0, win 2226/480, upem 2048 — identical across
both files, so line height is stable) · the monospace advance (1200) · PANOSE.

PANOSE weight stays at 6 (Medium) deliberately: it describes the weight the font *declares*, which
after the relabel is 400, not the master it was cut from.

Three things change as a consequence of restricting the axis, each of them correct:

| | why |
|---|---|
| `cvt `/`cvar` | `cvt ` is rebased onto the new default through `cvar`. The hinting *program* — `fpgm`, `prep`, and all 1363 (roman) / 1022 (italic) glyph bytecode streams — is byte-identical; only the control values it reads move, which is what a variable font's hinting is supposed to do at a new default. |
| `hmtx`/`hhea` | Advances stay 1200 everywhere; left side bearings follow the new default outlines, and `hhea`'s derived min/max fields follow the bearings. |
| `GSUB` `rvrn` | Dropped, with its 2 lookups. `rvrn` is upstream's required-variation feature, and its condition sets cover normalised design 0.0–1.0 — `wght` 400–700 in source terms. The cut sits at −0.500..−0.333, below every condition, so the feature could never fire here. `calt`, `rclt`, `rlig`, the `ssXX` sets and every other feature come through with their lookups intact. |

`DSIG` is dropped: any edit invalidates it.

## Licensing

Cascadia ships under an SIL OFL 1.1-based licence. Copyright (nameID 0), the full licence (13) and
licence URL (14) are preserved verbatim, as are the author and vendor acknowledgements — 8 "Saja
Typeworks", 9 "Aaron Bell", and the URLs in 11/12 — which clause 4 permits exactly. The family is
renamed, so clause 3 (Reserved Font Name) cannot bite whether or not Microsoft reserved
"Cascadia". The trademark line (nameID 7) is dropped, since these files are not Cascadia Code. No
licence text is altered (clause 5).

## What `validate.py` checks

159 checks across five stages. Non-zero exit if any of them fails, so it works as a CI gate.

1. **OTS** — both outputs must sanitize.
2. **Build scope.** Byte-identity is the wrong test for most tables here — restricting a variable
   axis legitimately rewrites `glyf`, `gvar`, `cvt `, `cvar`, `hmtx`, `hhea` and the variation
   stores in `GDEF`/`GPOS` — so the scope is proved four other ways:
   - **Outline equivalence across the axis.** Source and output are instanced at matching
     positions (source 325/337.5/350 against output 400/550/700) and every coordinate compared:
     62 279 points in the roman, 49 492 in the italic. Identical at the default; at most one unit
     elsewhere.
   - **Positioning equivalence.** Every GPOS value is compared on the *fully instanced* tables,
     where no variation data is left to explain a difference away. Identical at the default. This
     exists because the shaping stage cannot reach it: roughly half of Cascadia's 319 mark records
     belong to glyphs with no cmap entry — `uniFBBC.comb` and the other Arabic contextual forms —
     so only a direct table comparison sees them move.
   - **Hinting identity.** `fpgm`, `prep` and every glyph instruction stream byte-identical, plus
     `gasp`, `cmap` and `post`.
   - **Layout parity.** Every GSUB/GPOS feature survives with the same lookup count and types. The
     one feature allowed to vanish is one that had no lookups at the default and reached the font
     only through `FeatureVariations` records this cut can never satisfy. That is proved, not
     assumed: the cut's span is normalised into the source's own design space and every condition
     set checked disjoint from it, so a source update that moved those conditions into range would
     fail the run.
3. **Shaping** — the check that matters for a coding font. A corpus of operators, prose, accented
   and combining-mark text, RTL and box drawing, plus a generated `base + mark` probe for every
   combining mark the font maps, is shaped through source and output at both ends of the axis with
   HarfBuzz; the glyph *names* must match exactly and the positions to within the same one-unit
   floor. Then the ligature policy is asserted behaviourally: `-> => != === <=> |> :: ?. >= <-`
   must come out as plain characters at both weights.
4. **Structural / variable-font** — `fvar` axis 400‑400‑700 with exactly two named instances and
   the default one on nameIDs 2/6; `STAT` with Regular elided and linked to Bold plus the right
   `ital` value; RIBBI names, weight class and style bits; no Cascadia or Microsoft branding in the
   identity names (0/8/9/11–14 keep it, as attribution) and the trademark dropped; no NUL bytes;
   Windows-only name records; no DSIG; integer-PPEM `head.flags` bit; timestamps inherited from the
   source (the reproducibility guarantee); uniform advance widths at *both* weights; vertical
   metrics unchanged and identical across both files.
5. **fontbakery `check-universal`** — no FAIL beyond a small allowlist inherited from upstream
   Cascadia Mono: `arabic_high_hamza`, `case_mapping`, `family/win_ascent_and_descent`,
   `nested_components`, `smart_dropout`. Totals: PASS=174 FAIL=9.

The allowlist is verified rather than assumed, and the build's two stages were measured
separately:

| stage | new FAILs | fixed |
|---|---|---|
| raw source → axis cut only | `fvar/regular_coords_correct` (the axis says 325 while the names still say Regular) | — |
| axis cut → rebranded output | none | that one, plus `no_mac_entries` |

One WARN is expected and is *not* inherited: `points_out_of_bounds` fires on a single glyph,
`ninepersiansuperior`, whose composite bounding box rounds a unit short of a component point once
the default sits on the midpoint. The axis cut alone produces it, before any metadata is touched.
Which glyph trips it depends on where the default lands, so expect the name to move if the cut ever
does. fontbakery's own advice on this check is that fixing it usually does more harm than good.

### The checks are negative-tested

Sabotaging a built copy makes the run fail, each break caught by the specific check meant to catch
it — 10/10 mutations caught:

| mutation | caught by |
|---|---|
| axis max widened 700 → 800 | outline equivalence at the middle of the axis (worst deviation 7) |
| one point of glyph `A` moved 3 units | outline equivalence at the default |
| a byte prepended to `prep` | `prep` byte-identical to source |
| `calt` stripped of its lookups | GSUB lookup counts and types unchanged |
| one GPOS mark anchor moved 40 units | GPOS equivalence at the default |
| cmap entry for `a` repointed at `b` | shaping picks different glyphs |
| nameID 1 set back to "Cascadia Code" | family name, and the branding scan |
| Bold instance moved to wght 600 | named instance position |
| `STAT` Regular linked to 500 | STAT axis values |
| `sTypoAscender` bumped by 1 | vertical metrics, and the inherited-timestamp check |

Two of those were only caught after the gaps they exposed were closed. Stripping `calt` changes
nothing observable in a font that has no ligatures, so the shaping stage cannot see it — layout
parity is what guards it. And the mark-anchor move went undetected until the whole-GPOS comparison
was added, because the anchor belonged to a glyph no string can reach.

### Requirements

`fonttools`, `uharfbuzz`, `opentype-sanitizer` (`ots`), `fontbakery`. No `ttfautohint` — this
pipeline does not re-hint.
