# rnetonet build pipeline

Two scripts that reproduce and verify the `rnetonet` font family from its upstream sources.
The family is a rebrand of **Cascadia Code** (the ligature-carrying cut of Cascadia), with its
coding ligatures kept. The four RIBBI styles are produced by pinning the `wght` axis of
Cascadia Code's variable fonts, so the whole family derives from two source files.

```
rnetonet/
  sources/
    Cascadia_Code/              <- upstream Cascadia Code (build inputs)
      CascadiaCode.ttf                (variable, roman)
      CascadiaCodeItalic.ttf          (variable, italic)
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
| `CascadiaCode.ttf`       | 300 (Light)     | `rnetonet-Regular.ttf`       | 400 |
| `CascadiaCode.ttf`       | 350 (SemiLight) | `rnetonet-Bold.ttf`          | 700 |
| `CascadiaCodeItalic.ttf` | 300 (Light)     | `rnetonet-RegularItalic.ttf` | 400 |
| `CascadiaCodeItalic.ttf` | 350 (SemiLight) | `rnetonet-BoldItalic.ttf`    | 700 |

The Light instance becomes the family Regular and the SemiLight instance its Bold -- a
deliberately low-contrast pairing (only 50 axis units apart) -- so the four files bold- and
italic-link as one RIBBI family. Glyph outlines, TrueType hinting (`fpgm`/`prep`/`cvt`/`gasp`)
and layout tables (`GSUB`/`GPOS`, hence the `calt`/`liga` **ligatures**) pass through from the
pinned instance untouched; only naming, weight/style flags, STAT and vertical metrics are
rewritten. A 7-byte smart-dropout instruction is appended to `prep` (the static Cascadia builds
carry it; the variable fonts do not), and `head.flags` keeps its integer-PPEM bit since Cascadia
is manually hinted.

**OFL-1.1 compliance:** copyright (nameID 0), full license text (13), license URL (14) and
author acknowledgements (8/9) are preserved; the reserved family name is dropped by renaming
(clause 3) and the trademark line (nameID 7) is dropped. No license text is altered (clause 5).

## What `validate.py` checks

1. **OTS** — every output must sanitize.
2. **Structural / RIBBI** — shared family name, subfamilies, weight classes, `fsSelection` /
   `macStyle` style bits, integer-PPEM `head.flags` bit (hinted fonts), STAT present, `fvar`
   gone, smart-dropout present, uniform advance widths (monospace), Windows-only name records,
   no DSIG.
3. **Ligatures** — HarfBuzz-shaping coding sequences (`-> => != === >= <=` …) must differ from
   shaping with ligature features forced off, proving the ligatures still fire.
4. **fontbakery `check-universal`** — no FAIL beyond a small allowlist inherited from the
   upstream Cascadia design (`arabic_high_hamza`, `case_mapping`, `family/win_ascent_and_descent`,
   `nested_components`). Any new FAIL fails the run. The allowlist is verified by diffing against
   plain-instanced controls: the rebrand introduces zero new FAILs and fixes several the raw
   instance has (`smart_dropout`, `no_mac_entries`, `fsselection`, `mac_style`).

Exit code is non-zero if any stage fails, so `validate.py` works as a CI gate.

### Requirements

`fonttools`, `opentype-sanitizer` (`ots`), `fontbakery`, `uharfbuzz`.
