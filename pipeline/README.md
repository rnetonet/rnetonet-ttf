# rnetonet build pipeline

Two scripts that reproduce and verify the `rnetonet` font family from its upstream sources.
The family is a rebrand of **JetBrains Mono**, shifted one step lighter: JetBrains Mono's Light
ships as `rnetonet`'s Regular, and its Regular ships as `rnetonet`'s Bold.

The sources are already static, so nothing is instanced or interpolated and **no outline is ever
redrawn**. The build does two things: re-hints with tuned ttfautohint parameters, and rebrands the
metadata. `validate.py` proves the scope by comparing every glyph point coordinate against the
source and diffing every table the build has no business touching.

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
python pipeline/build.py       # re-hint + rebrand -> rnetonet/rnetonet-*.ttf
python pipeline/validate.py    # OTS + build-scope + structural/RIBBI + fontbakery gate
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

What changes:

| Table | Change |
|---|---|
| `fpgm` `prep` `glyf` `loca` `maxp` | re-hinted -- instruction streams only, coordinates untouched |
| `TTFA` | **added** by ttfautohint -- records every parameter used, so the hinting is auditable |
| `name`  | rebranded (see below), plus ttfautohint's version stamp in nameID 5 |
| `OS/2`  | `usWeightClass`, `fsSelection` style bits (+ `USE_TYPO_METRICS`, `WWS`) |
| `head`  | `macStyle` style bits |
| `STAT`  | **added** -- the sources ship none, and a RIBBI family should declare its axis positions |

Everything else passes through byte for byte: layout (`GSUB`/`GPOS`/`GDEF`), `cmap`, `hmtx`,
`hhea`, `post`, `cvt ` and `gasp`. To keep that literally true the script probes the layout tables
on a throwaway font handle -- reading `GSUB` through the font it saves would decompile it, and
fontTools would then repack it into different (though equivalent) bytes.

Vertical metrics (typo 1020/-300/0, win 1020/300, upem 1000) are identical across all four faces
and are kept exactly as shipped, so line height is stable across the family.

## Hinting

Upstream JetBrains Mono 2.304 is hinted with **stock ttfautohint defaults**. That is verified
rather than assumed: re-running ttfautohint with no options at all reproduces its `fpgm`, `prep`,
`cvt ` and `glyf` byte for byte. Defaults are generic, and two of them leave real quality on the
table for a coding font.

| Parameter | Default | Ours | Why |
|---|---|---|---|
| `fallback-script` | `none` | `latn` | `none` means every glyph outside a recognised script gets **no hinting at all** -- here that is 128 box-drawing glyphs, 32 block elements, 21 arrows, 62 math symbols and 43 geometric shapes: exactly what a terminal draws TUI borders, tables, tree views and progress bars with. Affects symbols only. |
| `dw-cleartype-stem-width-mode` | quantized | `strong` | The one that reaches almost everybody, and what improves **letters and digits**. |
| `gray-stem-width-mode` | quantized | `strong` | Only reaches FreeType's legacy v35 interpreter. |
| `gdi-cleartype-stem-width-mode` | strong | `strong` | Only reaches Windows GDI ClearType. Already the default; set anyway so the config is complete. |
| `TTFA-info` | off | on | Writes the `TTFA` table so a built font states how it was hinted. |

Which stem mode reaches which renderer is worth being precise about, because it is easy to get
backwards. ttfautohint emits a `prep` that branches on rendering mode. FreeType's default **v40
interpreter emulates ClearType**, so it takes the *DirectWrite* branch -- not the grayscale one.
Isolating each mode makes that unambiguous:

| variant | symbols | letters + digits | Bold/Regular ink ratio |
|---|---|---|---|
| upstream defaults | 0.4385 | 0.0744 | 1.1204 |
| `fallback-script=latn` alone | 0.4565 | 0.0744 | 1.1204 |
| `latn` + `gdi=strong` | 0.4565 | 0.0744 | 1.1204 |
| **`latn` + `dw=strong` (ours)** | **0.5169** | **0.1038** | 1.1115 |

Measured as the fraction of ink rendered at full saturation rather than smeared into half-grays,
over 9-18 ppem. So: **+17.9% on symbols and +39.5% on letters and digits.** The letter gain is not
extra weight -- total ink coverage moves -0.13%, meaning the same ink simply lands decisively
instead of blurring. Across the family the letter gain runs +25% (Bold) to +56% (Regular Italic),
counters stay fully open (1.000), and italic accent separation improves 0.826 -> 0.865.

**The one real cost.** Snapping stems to whole pixels narrows the Bold/Regular weight contrast
slightly, from a 1.1204 ink ratio to 1.1115 (-0.8%). That matters more here than it normally would,
because this family's Bold is only one step above its Regular (JetBrains Light 300 vs Regular 400),
so the contrast is modest to begin with. It is a small price for a large legibility gain, but if the
family ever reads as too flat between Regular and Bold, `dw-cleartype-stem-width-mode` is the dial:
`natural` restores the contrast (1.1231) and gives the crispness back up.

Rejected after measuring, not by taste -- recorded so none of it gets retried on a hunch:

| Rejected | Why |
|---|---|
| `hint-composites` | Identical metrics even on composite glyphs (accented letters, and the 27 composite ligature glyphs), and +53KB a face. Composites inherit their components' hinting, which is already correct. |
| `adjust-subglyphs` | Accent separation fell 0.865 -> 0.816, and +95KB a face. |
| `x-height-snapping-exceptions=6-16` | +1% crispness, but accent separation fell to 0.812. |
| `windows-compatibility` | Identical metrics, and it would rewrite the `usWin` metrics the family deliberately keeps as shipped. |
| `increase-x-height` 0/12/16/18 | No gain. |
| `hinting-range-max=72` | Identical even when measured at 52-72 ppem, the only range where it could matter. |
| shared `--reference` | The faces already agree on x-height, cap-height and baseline at every ppem from 9 to 24. |
| `fallback-scaling` | Actively harmful: accent separation collapsed 0.86 -> 0.16. |
| per-face stem modes | Regular `strong` + Bold `quantized`, to buy back the contrast above: recovers only +0.06% (1.1115 -> 1.1122) while costing Bold a fifth of its crispness gain. The contrast cost is inherent to grid-snapping, not to this particular setting. |
| `gasp` tuning | Built and installed as a separate family (`{20: 0x07, 65535: 0x0F}` -- no ClearType symmetric smoothing at or below 20 ppem) and compared side by side in a real editor on Windows/DirectWrite, since FreeType ignores `gasp` and the harness here is blind to it. **No visible difference**, so the variant was dropped and `gasp` stays exactly as upstream ships it. |

### Known limits of this tuning

The parameter search is exhausted, but the *quality* ceiling is not:

- **Control instructions are untouched.** ttfautohint's `control_file` allows per-glyph, per-ppem
  manual fixes, which is how a foundry polishes autohinting beyond what flags can reach. That is
  the biggest remaining lever, and it needs per-glyph visual review rather than a metric.
- **Only FreeType grayscale was measured.** DirectWrite, CoreText and subpixel/LCD ClearType were
  not -- they cannot be driven from this pipeline. The DirectWrite stem mode was chosen precisely
  because FreeType's v40 emulates ClearType, but real DirectWrite may still differ.
- **The metric is a proxy.** "Fraction of fully-saturated ink" tracks crispness; it is not
  legibility, and no systematic human review was done across the full character set.
- **The 153 ligature glyphs were never rendered.** They are not reachable by codepoint without
  shaping, so they were checked structurally (126 hinted, 27 composite and inheriting) rather than
  measured.

The smart-dropout instruction and the integer-PPEM `head.flags` bit both survive re-hinting, so
there is still no dropout patch to apply.

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
2. **Build scope** — `glyf` legitimately changes (instruction streams live in it), so byte-identity
   is the wrong test there; instead **every glyph point coordinate** is compared against the
   source, which is what "no outline was redrawn" actually means. Only the hinting tables
   (`fpgm`/`prep`/`glyf`/`loca`/`maxp`) and the metadata tables (`name`/`OS/2`/`head`) may differ;
   `STAT` and `TTFA` are the only additions; the layout, `cmap`, metric, `cvt ` and `gasp` tables
   must still be byte-identical. The `TTFA` table is then read back and asserted to carry the exact
   ttfautohint parameters the build commits to, so the hinting config cannot drift silently.
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

The checks are negative-tested: sabotaging a copy (moving one outline point by 1 unit, making the
TTFA table claim `fallback-script=none`, nudging a `cvt` value by 1, leaving the family name as
JetBrains Mono, smuggling a NUL into nameID 3, shifting `sTypoAscender`, dropping a stylistic-set
label) makes the run fail -- 7 of 7, each caught by the specific check meant to catch it.

### Requirements

`fonttools`, `ttfautohint-py`, `opentype-sanitizer` (`ots`), `fontbakery`.
