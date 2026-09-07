# rnetonet build pipeline

Two scripts that reproduce and verify the `rnetonet` font family from its upstream sources.
The family is a rebrand of **JetBrains Mono**, shifted one step lighter: JetBrains Mono's Light
ships as `rnetonet`'s Regular, and its Regular ships as `rnetonet`'s Bold.

The sources are already static, so nothing is instanced, interpolated or re-hinted. This is a
metadata rebrand and nothing more -- and `validate.py` proves it by diffing every other table
against the source byte for byte.

```
rnetonet/
  sources/                            <- upstream JetBrains Mono 2.304 (build inputs)
    JetBrainsMono-Light.ttf                 (300, roman)
    JetBrainsMono-LightItalic.ttf           (300, italic)
    JetBrainsMono-Regular.ttf               (400, roman)
    JetBrainsMono-Italic.ttf                (400, italic)
  rnetonet-Regular.ttf                <- build outputs (committed)
  rnetonet-Bold.ttf
  rnetonet-RegularItalic.ttf
  rnetonet-BoldItalic.ttf
pipeline/
  build.py
  validate.py
```

## Run

```sh
python pipeline/build.py       # rebrand -> rnetonet/rnetonet-*.ttf
python pipeline/validate.py    # OTS + rebrand-scope + structural/RIBBI + fontbakery gate
```

Both scripts resolve the repo root from their own location, so they run from any working
directory. They only write `rnetonet/`; sources are read, never modified.

## What `build.py` does

| Source | usWeightClass in | Output | usWeightClass out |
|---|---|---|---|
| `JetBrainsMono-Light.ttf`       | 300 | `rnetonet-Regular.ttf`       | 400 |
| `JetBrainsMono-Regular.ttf`     | 400 | `rnetonet-Bold.ttf`          | 700 |
| `JetBrainsMono-LightItalic.ttf` | 300 | `rnetonet-RegularItalic.ttf` | 400 |
| `JetBrainsMono-Italic.ttf`      | 400 | `rnetonet-BoldItalic.ttf`    | 700 |

Exactly four tables change:

| Table | Change |
|---|---|
| `name`  | rebranded -- see below |
| `OS/2`  | `usWeightClass`, `fsSelection` style bits (+ `USE_TYPO_METRICS`, `WWS`) |
| `head`  | `macStyle` style bits |
| `STAT`  | **added** -- the sources ship none, and a RIBBI family should declare its axis positions |

Everything else is passed through untouched: outlines (`glyf`/`loca`), the whole ttfautohint
hinting program (`fpgm`/`prep`/`cvt `/`gasp` and every per-glyph instruction stream), layout
(`GSUB`/`GPOS`/`GDEF`), `cmap`, `hmtx`, `hhea`, `maxp` and `post`. To keep that literally true the
script probes the layout tables on a throwaway font handle -- reading `GSUB` through the font it
saves would decompile it, and fontTools would then repack it into different (though equivalent)
bytes.

JetBrains Mono is hinted with **ttfautohint 1.8.4.7** and already carries the smart-dropout
instruction in `prep`, so there is no dropout patch to apply and `head.flags` already has its
integer-PPEM bit. Vertical metrics (typo 1020/-300/0, win 1020/300, upem 1000) are identical
across all four faces and are kept exactly as shipped, so line height is stable across the family.

**Ligatures are kept.** JetBrains Mono's coding ligatures live in `calt`, which passes through
untouched, so `-> => != ===` render as ligatures -- verified by shaping them through HarfBuzz in
all four faces. Worth knowing if you were relying on a ligature-free base: JetBrains ships an
`NL` no-ligature cut, and swapping the four source files for it needs no pipeline change.

The `cvXX` character variants and `ssXX` stylistic sets survive too, including the four UI labels
`GSUB` points at -- "Classic construction", "Closed construction", "Broken equals ligatures",
"Rased bar f" -- which are found by walking the layout tables rather than being hardcoded, so the
256+ name purge cannot orphan them.

**OFL-1.1 compliance:** copyright (nameID 0), full license text (13), license URL (14) and author
acknowledgements (8/9, plus vendor/designer URLs 11/12) are preserved; the family is renamed and
the trademark line (nameID 7) is dropped, since the result is not JetBrains Mono. JetBrains Mono
carries no Reserved Font Name, so clause 3 does not bite -- the rename is about not passing the
derivative off as the original. No license text is altered (clause 5).

One upstream trap worth naming: `achVendID` is NUL-padded (`'JB\0\0'`), and `str.strip()` does not
remove NULs -- composing nameID 3 from it naively smuggles NUL bytes into the name table.
`build.py` strips them and `validate.py` guards the whole table against them.

## What `validate.py` checks

1. **OTS** — every output must sanitize.
2. **Rebrand scope** — every table except `name`/`OS/2`/`head` must be byte-identical to the
   JetBrains Mono file it was built from, and `STAT` must be the only table added. One sweep
   covers outlines, the full hinting program, and the layout tables that carry the ligatures;
   the hinting and outline tables are also asserted individually so a failure names the culprit.
3. **Structural / RIBBI** — shared family name, subfamilies, weight classes, `fsSelection` /
   `macStyle` style bits, no JetBrains branding left in the identity names (0/8/9/11-14 keep it,
   as attribution), trademark dropped, no NUL bytes in any name record, integer-PPEM `head.flags`
   bit, STAT present, no `fvar` (these are statics), smart-dropout present in `prep`, stylistic-set
   UI labels still resolving, vertical metrics unchanged and consistent across the family, uniform
   advance widths (monospace), Windows-only name records, no DSIG.
4. **fontbakery `check-universal`** — no FAIL beyond a small allowlist inherited from upstream
   JetBrains Mono (`case_mapping`, `empty_letters`, `family/win_ascent_and_descent`). Any new FAIL
   fails the run. The allowlist is verified by running the same profile over the untouched sources:
   the rebrand introduces zero new FAILs and zero new WARNs, and fixes two the sources have
   (`no_mac_entries`, `opentype/STAT/ital_axis`).

Exit code is non-zero if any stage fails, so `validate.py` works as a CI gate.

The checks are negative-tested: sabotaging a copy (stripping one glyph's instructions, nudging a
`cvt` value by 1, leaving the family name as JetBrains Mono, smuggling a NUL into nameID 3,
shifting `sTypoAscender`, dropping a stylistic-set label) makes the run fail, each caught by the
specific check meant to catch it.

### Requirements

`fonttools`, `opentype-sanitizer` (`ots`), `fontbakery`.
