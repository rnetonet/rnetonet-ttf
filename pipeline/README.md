# rnetonet build pipeline

Two scripts that reproduce and verify the `rnetonet` font family from its upstream sources.
The family is a rebrand of **JetBrains Mono**, with its coding ligatures kept. The four RIBBI
styles are produced by pinning the `wght` axis of JetBrains' variable fonts, so the whole
family derives from two source files.

```
rnetonet/
  sources/
    JetBrains_Mono/             <- upstream JetBrains Mono (build inputs)
      JetBrainsMono[wght].ttf         (variable, roman)   <- used
      JetBrainsMono-Italic[wght].ttf  (variable, italic)  <- used
      JetBrainsMono-*.ttf             (static weights)    <- archived, not built from
    Cascadia_Mono/              <- previous design's sources, kept for reference only
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
python pipeline/validate.py    # OTS + structural/RIBBI + ligatures + fontbakery gate
```

Both scripts resolve the repo root from their own location, so they run from any working
directory. They only touch `rnetonet/`; sources are read, never modified.

## What `build.py` does

Per style, in a single pass (so no later step can orphan a name record):

| Source (variable) | `wght` pinned | Output | usWeightClass |
|---|---|---|---|
| `JetBrainsMono[wght].ttf`        | 350 (SemiLight) | `rnetonet-Regular.ttf`       | 400 |
| `JetBrainsMono[wght].ttf`        | 400 (Regular)   | `rnetonet-Bold.ttf`          | 700 |
| `JetBrainsMono-Italic[wght].ttf` | 350 (SemiLight) | `rnetonet-RegularItalic.ttf` | 400 |
| `JetBrainsMono-Italic[wght].ttf` | 400 (Regular)   | `rnetonet-BoldItalic.ttf`    | 700 |

The SemiLight instance (350, midway between JetBrains' Light 300 and Regular 400) becomes the
family Regular and the Regular instance its Bold, so the four files bold- and italic-link as one
RIBBI family. Glyph outlines and layout tables (`GSUB`/`GPOS`, hence the `calt`/`liga`
**ligatures**) pass through from the pinned instance untouched; only naming, weight/style flags,
STAT and vertical metrics are rewritten.

JetBrains Mono is not fpgm/cvt-hinted -- it uses `gasp` smoothing plus a smart-dropout `prep`
(both already in the source), so this build does not force the integer-PPEM `head.flags` bit
(that applies only to manually hinted fonts, as the Cascadia design it replaces was).

**OFL-1.1 compliance:** copyright (nameID 0), full license text (13), license URL (14) and
author acknowledgements (8/9 -- JetBrains / Philipp Nurullin, Konstantin Bulenkov) are
preserved; the reserved family name is dropped by renaming (clause 3) and the trademark line
(nameID 7) is dropped. No license text is altered (clause 5).

## What `validate.py` checks

1. **OTS** — every output must sanitize.
2. **Structural / RIBBI** — shared family name, subfamilies, weight classes, `fsSelection` /
   `macStyle` style bits, STAT present, `fvar` gone, smart-dropout present, uniform advance
   widths (monospace), Windows-only name records, no DSIG.
3. **Ligatures** — HarfBuzz-shaping coding sequences (`-> => != === >= <=` …) must differ from
   shaping with ligature features forced off, proving the ligatures still fire.
4. **fontbakery `check-universal`** — no FAIL beyond one allowlisted FAIL inherited from
   upstream JetBrains Mono (`empty_letters`: U+16910 ships as an empty glyph). Any new FAIL
   fails the run. The allowlist is verified by diffing against plain-instanced controls: the
   rebrand introduces zero new FAILs and fixes several the raw instance has.

Exit code is non-zero if any stage fails, so `validate.py` works as a CI gate.

### Requirements

`fonttools`, `opentype-sanitizer` (`ots`), `fontbakery`, `uharfbuzz`.
