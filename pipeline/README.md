# rnetonet build pipeline

Two scripts that reproduce and verify the `rnetonet` font family from its upstream sources.
The family is a rebrand of **Cascadia Code** -- the cut of Cascadia that ships coding ligatures.
The four RIBBI styles are produced by pinning the `wght` axis of Cascadia Code's variable fonts,
so the whole family derives from two source files.

```
rnetonet/
  sources/                      <- upstream Cascadia Code (build inputs)
    CascadiaCode.ttf                  (variable, roman)
    CascadiaCodeItalic.ttf            (variable, italic)
  rnetonet-Regular.ttf          <- build outputs (committed)
  rnetonet-Bold.ttf
  rnetonet-RegularItalic.ttf
  rnetonet-BoldItalic.ttf
pipeline/
  build.py
  validate.py
```

## Run

```sh
python pipeline/build.py       # instance + rebrand -> rnetonet/rnetonet-*.ttf
python pipeline/validate.py    # OTS + structural/RIBBI + fontbakery gate
```

Both scripts resolve the repo root from their own location, so they run from any working
directory. They only touch `rnetonet/`; sources are read, never modified.

## What `build.py` does

Per style, in a single pass (so no later step can orphan a name record):

| Source (variable) | `wght` pinned | Output | usWeightClass |
|---|---|---|---|
| `CascadiaCode.ttf`       | 337.5 (Light..SemiLight)   | `rnetonet-Regular.ttf`       | 400 |
| `CascadiaCode.ttf`       | 362.5 (SemiLight..Regular) | `rnetonet-Bold.ttf`          | 700 |
| `CascadiaCodeItalic.ttf` | 337.5 (Light..SemiLight)   | `rnetonet-RegularItalic.ttf` | 400 |
| `CascadiaCodeItalic.ttf` | 362.5 (SemiLight..Regular) | `rnetonet-BoldItalic.ttf`    | 700 |

The Regular is pinned at wght 337.5 -- between Cascadia's Light (300) and SemiLight (350) named
instances, just below SemiLight (instancing accepts any axis value, not just named ones) -- and
the Bold at wght 362.5, just above SemiLight toward Regular (400). It is a deliberately
low-contrast pairing (only 25 axis units apart), so the four files bold- and italic-link as one
RIBBI family.

Cascadia Code is already TrueType-instruction hinted (`fpgm`/`prep`/`cvt`/`gasp`), and that hinting
passes straight through the instancer untouched -- **no ttfautohint pass is applied**. Glyph
outlines, hinting and layout tables (`GSUB`/`GPOS`) pass through from the pinned instance untouched;
only naming, weight/style flags, STAT and vertical metrics are rewritten. A 7-byte smart-dropout
instruction is appended to `prep` (the static Cascadia builds carry it; the variable fonts do not),
and `head.flags` keeps its integer-PPEM bit since Cascadia is manually hinted. Cascadia Code's
coding ligatures (`calt`/`rclt`/`rlig`) live in that untouched GSUB, so they survive intact, along
with the contextual alternates and stylistic sets whose UI name labels are preserved.

**OFL-1.1 compliance:** copyright (nameID 0), full license text (13), license URL (14) and
author acknowledgements (8/9) are preserved; the reserved family name is dropped by renaming
(clause 3) and the trademark line (nameID 7) is dropped. No license text is altered (clause 5).

## What `validate.py` checks

1. **OTS** — every output must sanitize.
2. **Structural / RIBBI** — shared family name, subfamilies, weight classes, `fsSelection` /
   `macStyle` style bits, integer-PPEM `head.flags` bit (asserted since Cascadia is `fpgm`/`cvt`
   hinted), STAT present, `fvar` gone, smart-dropout present, uniform advance widths (monospace),
   Windows-only name records, no DSIG.
3. **Coding ligatures** — each output still shapes Cascadia's coding ligatures: probe sequences
   (`-> => != === >= <= <- |>`) must map to different glyphs with default features than with
   `calt`/`rclt`/`liga` off (HarfBuzz), proving the passed-through GSUB kept them.
4. **fontbakery `check-universal`** — no FAIL beyond a small allowlist inherited from the
   upstream Cascadia design (`arabic_high_hamza`, `case_mapping`, `family/win_ascent_and_descent`,
   `nested_components`). Any new FAIL fails the run. The allowlist is verified by diffing against
   plain-instanced controls: the rebrand introduces zero new FAILs and fixes several the raw
   instance has (`smart_dropout`, `no_mac_entries`).

Exit code is non-zero if any stage fails, so `validate.py` works as a CI gate.

### Requirements

`fonttools`, `opentype-sanitizer` (`ots`), `fontbakery`, `uharfbuzz`.
