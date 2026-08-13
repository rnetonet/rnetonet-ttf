# rnetonet build pipeline

Two scripts that reproduce and verify the `rnetonet` font family from its upstream sources.
The family is a rebrand of **JetBrains Mono**, with its coding ligatures kept and a fresh
**ttfautohint** hinting pass added for crisp rendering on Windows/DirectWrite (VS Code). The four
RIBBI styles are produced by pinning the `wght` axis of JetBrains Mono's variable fonts, so the
whole family derives from two source files.

```
rnetonet/
  sources/
    JetBrains_Mono/                 <- upstream JetBrains Mono (build inputs)
      JetBrainsMono[wght].ttf             (variable, roman)
      JetBrainsMono-Italic[wght].ttf      (variable, italic)
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

The Regular is pinned at wght 350 -- a "SemiLight" between JetBrains' Light (300) and Regular
(400) named instances (instancing accepts any axis value, not just named ones) -- and the Regular
instance (400) becomes the Bold. It is a deliberately low-contrast pairing (only 50 axis units
apart), so the four files bold- and italic-link as one RIBBI family.

Each pinned instance is **hinted with ttfautohint** before rebranding. JetBrains' variable fonts
carry no TrueType instructions (only a `gasp` and a smart-dropout `prep`), so the raw instance is
effectively unhinted and renders soft on Windows/DirectWrite. ttfautohint adds a full instruction
set (`fpgm`/`prep`/`cvt` + per-glyph programs on ~99% of non-empty glyphs) tuned aggressively for
Windows: range 8..96 ppem with no upper limit, Windows-compatibility blue zones, `latin` default
and fallback scripts (so symbols and box-drawing are hinted too), composite hinting, and *strong*
stem-width snapping for grayscale, GDI **and** DirectWrite ClearType so stems land on whole pixels.
`head.flags` bit 3 (force-integer-ppem) is set so the hints don't misfire at fractional ppem, and a
`TTFA` table records the exact options used. This roughly doubles each file (~200 KB -> ~420 KB).

Glyph outlines and layout tables (`GSUB`/`GPOS`, hence the `calt`/`liga` **ligatures**) pass
through untouched; ttfautohint only adds instructions, and only naming, weight/style flags, STAT
and vertical metrics are rewritten afterwards.

**OFL-1.1 compliance:** copyright (nameID 0), full license text (13), license URL (14) and
author acknowledgements (8/9) are preserved; the reserved family name is dropped by renaming
(clause 3) and the trademark line (nameID 7) is dropped. No license text is altered (clause 5).

## What `validate.py` checks

1. **OTS** — every output must sanitize.
2. **Structural / RIBBI** — shared family name, subfamilies, weight classes, `fsSelection` /
   `macStyle` style bits, ttfautohint hinting present (`fpgm`/`prep`/`cvt`/`gasp` + `TTFA` +
   force-integer-ppem `head.flags` bit + per-glyph instructions on >95% of non-empty glyphs),
   STAT present, `fvar` gone, smart-dropout present, uniform advance widths (monospace),
   Windows-only name records, no DSIG.
3. **Ligatures** — HarfBuzz-shaping coding sequences (`-> => != === >= <=` …) must differ from
   shaping with ligature features forced off, proving the ligatures still fire.
4. **fontbakery `check-universal`** — no FAIL beyond a small allowlist inherited from the
   upstream JetBrains Mono design (`empty_letters`: a few glyphs such as NBSP intentionally have
   no outline). Any new FAIL fails the run. The allowlist is verified by diffing against
   instanced-and-hinted controls (same ttfautohint pass, no rebrand): the rebrand introduces zero
   new FAILs, fixes `no_mac_entries`, and the hinting's `integer_ppem_if_hinted` FAIL is resolved
   by setting the force-integer-ppem `head.flags` bit.

Exit code is non-zero if any stage fails, so `validate.py` works as a CI gate.

### Requirements

`fonttools`, `ttfautohint-py`, `opentype-sanitizer` (`ots`), `fontbakery`, `uharfbuzz`.
