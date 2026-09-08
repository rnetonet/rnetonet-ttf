# rnetonet build pipeline

Two scripts that reproduce and verify the `rnetonetcode` and `rnetonetmono` variable font
families from their upstream sources. Both are rebrands of **Cascadia**, shifted one step lighter:
Cascadia's Light ships as Regular and its SemiLight ships as Bold.

Nothing is redrawn and nothing is re-hinted. The build cuts Cascadia's weight axis down to the
Light..SemiLight span, relabels that span as 400..700 so the OS reads a Regular and a Bold, and
rebrands the metadata. `validate.py` proves the scope by instancing source and output at matching
positions and comparing every glyph coordinate, by re-shaping a text corpus through both with
HarfBuzz, and by diffing every table the build has no business touching.

```
rnetonet/
  sources/                            <- upstream Cascadia 2407.024 (build inputs)
    CascadiaCode.ttf                        wght 200-400-700, roman, with ligatures
    CascadiaCodeItalic.ttf                  wght 200-400-700, italic, with ligatures
    CascadiaMono.ttf                        the same, ligatures removed
    CascadiaMonoItalic.ttf
  rnetonetcode-Roman.ttf              <- build outputs (committed)
  rnetonetcode-Italic.ttf
  rnetonetmono-Roman.ttf
  rnetonetmono-Italic.ttf
pipeline/
  build.py
  validate.py
```

`rnetonetcode` keeps Cascadia Code's programming ligatures; `rnetonetmono` is the ligature-free
cut. Upstream ships them as separate files whose `glyf` and `cmap` are byte-identical — the only
difference is `calt`, which carries 116 lookups in Code and 1 in Mono.

Filenames deliberately avoid the `Family[wght].ttf` convention: a literal `[wght]` is a glob
bracket expression and quietly breaks shell and Python globbing. `-Roman`/`-Italic` mirrors
upstream's own `CascadiaCodeRoman` variations prefix and globs cleanly.

## Run

```sh
python pipeline/build.py       # cut + relabel + rebrand -> rnetonet/rnetonet{code,mono}-*.ttf
python pipeline/validate.py    # OTS + build-scope + shaping + structural + fontbakery gate
```

Both scripts resolve the repo root from their own location, so they run from any working
directory. They only write `rnetonet/`; sources are read, never modified.

The build is **byte-reproducible**: two runs produce identical files. `head.modified` was the only
thing that differed before `build.py` started passing `recalcTimestamp=False`, so the committed
binaries can be re-derived and compared byte for byte against the sources plus the script.

## What `build.py` does

Each output is one source file, cut and relabelled:

| Source | wght in | Output | wght out |
|---|---|---|---|
| `CascadiaCode.ttf`        | 200‑400‑700 | `rnetonetcode-Roman.ttf`  | 400‑400‑700 |
| `CascadiaCodeItalic.ttf`  | 200‑400‑700 | `rnetonetcode-Italic.ttf` | 400‑400‑700 |
| `CascadiaMono.ttf`        | 200‑400‑700 | `rnetonetmono-Roman.ttf`  | 400‑400‑700 |
| `CascadiaMonoItalic.ttf`  | 200‑400‑700 | `rnetonetmono-Italic.ttf` | 400‑400‑700 |

Two named instances per file, and no more:

| Output instance | wght | is upstream's |
|---|---|---|
| Regular / Italic       | 400 | Light 300 |
| Bold / Bold Italic     | 700 | SemiLight 350 |

### 1. The cut

`instancer.instantiateVariableFont(font, {"wght": (300, 300, 350)})` keeps the font variable,
restricts the axis to the 300–350 span, and moves the default onto 300. `glyf` then holds the
Light outlines, `cvt ` holds the Light control values rebased through `cvar`, and
`gvar`/`HVAR`/`GDEF` carry only the deltas that reach from Light to SemiLight.

`optimize=False` turns off IUP delta re-optimization. That is a correctness choice, not a speed
one: IUP optimization drops deltas that interpolation can reproduce to within half a unit, and
that tolerance stacks on the rounding the default rebase already costs. Measured over every point
of every glyph, against the source pinned at the matching position:

| | worst deviation | roman face size |
|---|---|---|
| `optimize=True`  | 2 units at the Bold end | 595 KB |
| `optimize=False` | 1 unit anywhere         | 633 KB |

One unit (1/2048 em) is a floor, not a tunable. Upstream did not draw Light on integer
coordinates — it is an interpolation of Cascadia's masters — so rebasing the default onto it must
round, and the Bold deltas then round against that rounded default. 6% file size to keep the whole
axis at that floor is worth paying in a pipeline whose promise is that nothing was redrawn.

### 2. The relabel

`fvar`'s user-space endpoints are rewritten from 300/300/350 to 400/400/700. This is pure
relabelling and cannot move an outline: variation deltas live in *normalised* space (−1..1) and
`avar` maps normalised to normalised, so the only thing an `fvar` min/default/max triple decides
is how a user-space number is projected onto that normalised range. Both triples project
300 → 0.0 and 350 → 1.0, so `wght=400` renders exactly what `wght=300` did, `wght=700` exactly
what 350 did, and `wght=550` the midpoint either way.

The span is affine because upstream's `avar` happens to have breakpoints exactly at the two
weights being cut — normalised −0.5 → −0.66669 (Light) and −0.25 → −0.33331 (SemiLight) — so the
segment between them is a straight line. `validate.py` re-derives that span from the source and
checks the middle of the axis, not just the two ends, so a source whose `avar` moved would fail
rather than quietly bend.

**Why relabel at all.** The family has to *say* Regular and Bold. Left at 300–350, the OS reads a
Light family: `usWeightClass` 300, `font-weight: 400` resolving to the lighter end, and every
RIBBI convention in the OpenType stack arguing with the file. Relabelled, `font-weight: 400` is
the Regular, `700` is the Bold, and everything between stays continuously variable.

### 3. The contrast this buys

Bold carries **1.2535×** the ink of Regular — outline area over the 62 ASCII alphanumerics, source
instanced at 350 against 300. For reference, across upstream's full axis:

| upstream instance | ink vs Light |
|---|---|
| ExtraLight 200 | 0.74× |
| **Light 300** (our Regular) | 1.00× |
| **SemiLight 350** (our Bold) | **1.25×** |
| Regular 400 | 1.50× |
| SemiBold 600 | 1.74× |
| Bold 700 | 1.89× |

That is a light bold on purpose, and it is *more* contrast than the JetBrains-based `rnetonet`
this replaces shipped at 1.1203 — so the preference that family was tuned around survives the
move to Cascadia.

### 4. The rebrand

Family, subfamily, unique ID, full name, PostScript name and the variations PostScript prefix
(nameID 25) are rewritten; `fvar` gets its two named instances, the default one reusing nameIDs 2
and 6 rather than minting new records; `STAT` is rebuilt with a two-value `wght` axis (Regular
elided and linked to Bold) and an `ital` axis; `OS/2` and `head` get the weight class and style
bits that go with a Regular default — no file is "bold" at its default, because Bold lives on the
axis.

Name records for `fvar` and `STAT` are interned, so a file carries one "Weight" and one "Bold"
record rather than the duplicates each builder would otherwise mint.

## What is preserved, and what necessarily moves

Untouched, and checked table by table:

`glyf` outlines and instruction streams · `fpgm` · `prep` · `gasp` · `cmap` · `post` ·
`GSUB` lookups · `GPOS` · vertical metrics (typo 1900/−480/0, win 2226/480, upem 2048 — identical
across all four files, so line height is stable across both families) · the monospace advance
(1200) · PANOSE.

PANOSE weight stays at 6 (Medium) deliberately: it describes the weight the font *declares*, which
after the relabel is 400, not the master it was cut from.

Three things change as a consequence of restricting the axis, each of them correct:

| | why |
|---|---|
| `cvt `/`cvar` | `cvt ` is rebased onto the new default through `cvar`. The hinting *program* — `fpgm`, `prep`, and every glyph's bytecode — is byte-identical; only the control values it reads move, which is what a variable font's hinting is supposed to do at a new default. |
| `hmtx`/`hhea` | Advances stay 1200 everywhere; left side bearings follow the Light outlines, and `hhea`'s derived min/max fields follow the bearings. |
| `GSUB` `rvrn` | Dropped, with its 2 lookups. `rvrn` is upstream's required-variation feature, and its condition sets cover normalised design 0.0–1.0 — `wght` 400–700 in source terms. The cut sits at −0.667..−0.333, below every condition, so the feature could never fire here. `calt`, `rclt`, `rlig`, the `ssXX` sets and every other feature come through with their lookups intact. |

`DSIG` is dropped: any edit invalidates it.

## Licensing

Cascadia ships under an SIL OFL 1.1-based licence. Copyright (nameID 0), the full licence (13) and
licence URL (14) are preserved verbatim, as are the author and vendor acknowledgements — 8 "Saja
Typeworks", 9 "Aaron Bell", and the URLs in 11/12 — which clause 4 permits exactly. The family is
renamed, so clause 3 (Reserved Font Name) cannot bite whether or not Microsoft reserved
"Cascadia". The trademark line (nameID 7) is dropped, since these files are not Cascadia Code. No
licence text is altered (clause 5).

## What `validate.py` checks

306 checks across five stages. Non-zero exit if any of them fails, so it works as a CI gate.

1. **OTS** — every output must sanitize.
2. **Build scope.** Byte-identity is the wrong test for most tables here — restricting a variable
   axis legitimately rewrites `glyf`, `gvar`, `cvt `, `cvar`, `hmtx`, `hhea` and the variation
   stores in `GDEF`/`GPOS` — so the scope is proved three other ways:
   - **Outline equivalence across the axis.** Source and output are instanced at matching
     positions (source 300/325/350 against output 400/550/700) and every coordinate is compared:
     ~62k points per roman face, ~49k per italic. Identical at the default; at most one unit
     elsewhere.
   - **Hinting identity.** `fpgm`, `prep` and all 1363 (roman) / 1022 (italic) glyph instruction
     streams byte-identical, plus `gasp`, `cmap` and `post`.
   - **Layout parity.** Every GSUB/GPOS feature survives with the same lookup count and types. The
     one feature allowed to vanish is one that had no lookups at the default and reached the font
     only through `FeatureVariations` records this cut can never satisfy. That is proved, not
     assumed: the cut's span is normalised into the source's own design space and every condition
     set is checked disjoint from it, so a source update that moved those conditions into range
     would fail the run.
3. **Shaping** — the check that actually matters for a coding font. A corpus of operators, prose,
   accented and combining-mark text, RTL and box drawing is shaped through source and output at
   both ends of the axis with HarfBuzz; the glyph *names* must match exactly and the positions to
   within the same one-unit floor. Then the family split is asserted behaviourally: `rnetonetcode`
   must ligate `-> => != === <=> |> :: ?. >= <-` at both weights, and `rnetonetmono` must leave
   every one of them as plain characters.
4. **Structural / variable-font** — `fvar` axis 400‑400‑700 with exactly two named instances and
   the default one on nameIDs 2/6; `STAT` with Regular elided and linked to Bold plus the right
   `ital` value; RIBBI names, weight class and style bits; no Cascadia or Microsoft branding in the
   identity names (0/8/9/11–14 keep it, as attribution) and the trademark dropped; no NUL bytes;
   Windows-only name records; no DSIG; integer-PPEM `head.flags` bit; timestamps inherited from
   the source (the reproducibility guarantee); uniform advance widths at *both* weights; vertical
   metrics unchanged and identical across all four files.
5. **fontbakery `check-universal`**, run once per family — running both together produces nothing
   but "inconsistent family name" noise, since these are two families. No FAIL beyond a small
   allowlist inherited from upstream Cascadia: `arabic_high_hamza`, `case_mapping`,
   `family/win_ascent_and_descent`, `nested_components`, `smart_dropout`. Each family reports
   PASS=174 FAIL=9.

The allowlist is verified rather than assumed, and the build's two stages were measured
separately:

| stage | new FAILs | fixed |
|---|---|---|
| raw source → axis cut only | `fvar/regular_coords_correct`, `varfont/valid_default_instance_nameids` (the axis says 300 while the names still say Regular) | — |
| axis cut → rebranded output | none | both of the above, plus `no_mac_entries` |

One WARN is expected and is *not* inherited: `points_out_of_bounds` fires on one Arabic contextual
form, `uni0777.fina`, whose composite bounding box rounds one unit short of a component point once
the default sits on Light. The source instanced at Light has it too. fontbakery's own advice on
this check is that fixing it usually does more harm than good.

### The checks are negative-tested

Sabotaging a built copy makes the run fail, each break caught by the specific check meant to catch
it — 8/8 mutations caught:

| mutation | caught by |
|---|---|
| axis max widened 700 → 800 | outline equivalence at the middle of the axis (worst deviation 14) |
| one point of glyph `A` moved 3 units | outline equivalence at the default |
| a byte prepended to `prep` | `prep` byte-identical to source |
| `calt` stripped of its lookups | shaping picks different glyphs; ligature policy |
| nameID 1 set back to "Cascadia Code" | family name, and the branding scan |
| Bold instance moved to wght 600 | named instance position |
| `STAT` Regular linked to 500 | STAT axis values |
| `sTypoAscender` bumped by 1 | vertical metrics unchanged, and consistent across the family |

### Requirements

`fonttools`, `uharfbuzz`, `opentype-sanitizer` (`ots`), `fontbakery`. No `ttfautohint` — this
pipeline does not re-hint.
