# rnetonet build pipeline

Two scripts that reproduce and verify the `rnetonet` font family from its upstream sources.
The family is a rebrand of the ligature-free **Cascadia Mono** design: the four RIBBI styles
are produced by pinning the `wght` axis of Microsoft's variable CascadiaMono fonts.

```
rnetonet/
  sources/                    <- upstream variable fonts (inputs, committed)
    CascadiaMono.ttf
    CascadiaMonoItalic.ttf
  rnetonet-Regular.ttf        <- build outputs (committed)
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
python pipeline/validate.py    # OTS + structural/RIBBI + fontbakery gate (exit 0 = clean)
```

Both scripts resolve the repo root from their own location, so they run from any working
directory. They only touch `rnetonet/`; sources are read, never modified.

## What `build.py` does

Per style, in a single pass (so no later step can orphan a name record):

| Source (variable) | `wght` pinned | Output | usWeightClass |
|---|---|---|---|
| `CascadiaMono.ttf`       | 350 (SemiLight) | `rnetonet-Regular.ttf`       | 400 |
| `CascadiaMono.ttf`       | 400 (Regular)   | `rnetonet-Bold.ttf`          | 700 |
| `CascadiaMonoItalic.ttf` | 350 (SemiLight) | `rnetonet-RegularItalic.ttf` | 400 |
| `CascadiaMonoItalic.ttf` | 400 (Regular)   | `rnetonet-BoldItalic.ttf`    | 700 |

The SemiLight instance becomes the family Regular and the Regular instance its Bold, so the
four files bold- and italic-link as one RIBBI family. Glyph outlines, TrueType hinting
(`fpgm`/`prep`/`cvt`/`gasp`) and layout tables pass through from the pinned instance untouched;
only naming, weight/style flags, STAT and vertical metrics are rewritten. A 7-byte
smart-dropout instruction is appended to `prep` (the static Cascadia builds carry it; the
variable fonts do not).

**OFL-1.1 compliance:** copyright (nameID 0), full license text (13), license URL (14) and
author acknowledgements (8/9) are preserved; the reserved family name is dropped by renaming
(clause 3) and the trademark line (nameID 7) is dropped. No license text is altered (clause 5).

## What `validate.py` checks

1. **OTS** — every output must sanitize.
2. **Structural / RIBBI** — shared family name, subfamilies, weight classes, `fsSelection` /
   `macStyle` style bits, STAT present, `fvar` gone, smart-dropout present, uniform advance
   widths (monospace), Windows-only name records, no DSIG.
3. **fontbakery `check-universal`** — no FAIL beyond a small allowlist of FAILs inherited from
   upstream Cascadia Mono or from deliberate design choices (`arabic_high_hamza`,
   `case_mapping`, `family/win_ascent_and_descent`, `nested_components`). Any new FAIL fails
   the run.

Exit code is non-zero if any stage fails, so `validate.py` works as a CI gate.

### Requirements

`fonttools`, `opentype-sanitizer` (`ots`), `fontbakery`, `uharfbuzz`.
