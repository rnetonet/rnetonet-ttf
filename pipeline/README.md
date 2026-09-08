# rnetonet build pipeline

Two scripts that reproduce and verify the `rnetonet` font family from its upstream sources.
The family is a rebrand of **JetBrains Mono**, shifted one step lighter: JetBrains Mono's Light
ships as `rnetonet`'s Regular, and its Regular ships as `rnetonet`'s Bold.

The sources are already static, so nothing is instanced or interpolated and **no outline is ever
redrawn**. The build does two things: re-hints -- close to stock ttfautohint settings, with a latin
fallback script so the symbol glyphs get hinted too and the softest stem width mode so the letters
do not read brittle -- and rebrands the metadata. `validate.py` proves the scope by comparing every glyph point coordinate against the
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
`cvt ` and `glyf` byte for byte. Two of those defaults are changed here.

| Parameter | Default | Ours | Why |
|---|---|---|---|
| `fallback-script` | `none` | `latn` | `none` means every glyph outside a recognised script gets **no hinting at all** -- here that is 128 box-drawing glyphs, 32 block elements, 21 arrows, 62 math symbols and 43 geometric shapes: exactly what a terminal draws TUI borders, tables, tree views and progress bars with. Affects symbols only. |
| `gray-` and `dw-cleartype-stem-width-mode` | `quantized` | `natural` | The softest setting ttfautohint has: stem widths are not pulled towards the pixel grid at all, so edges keep their fractional coverage. Upstream's `quantized` read harder-edged than this family wants. Affects letters, digits and punctuation. |
| `gdi-cleartype-stem-width-mode` | `strong` | *unchanged* | Only Windows GDI ClearType takes that branch, and nothing in this pipeline can render it -- softening it would be a change made blind. |
| `TTFA-info` | off | on | Writes the `TTFA` table so a built font states how it was hinted. |

So the shipped hinting is exactly `ttfautohint --fallback-script=latn --stem-width-mode=nsn`, and
the build reproduces that byte for byte.

### The stem-width modes, and how this family ended up on `natural`

The three modes differ only in how far a stem width may be pulled towards the pixel grid, and this
family has now been through all three:

| mode | effect | symbols | letters + digits | Bold/Regular ink ratio |
|---|---|---|---|---|
| `natural` | **shipped**; no rounding at all, softest | 0.2978 | 0.0786 | 1.1236 |
| `quantized` | ttfautohint's default, and what upstream JetBrains Mono ships | 0.3041 | 0.0800 | 1.1203 |
| `strong` | stems snapped onto whole pixels; crispest | 0.3819 | 0.1059 | 1.0938 |

`strong` was set in commit `34aed65` and reverted in `5bbd30c`: it measured far crisper and **read
brittle in daily use**. `natural` is the same axis in the other direction, and the honest headline
is that it is a *small* move -- -1.7% on letters and digits, -2.1% on symbols, against the +32%
`strong` had added. Stem width mode is the only softness flag ttfautohint offers and this is its
softest setting; if the family still reads too hard, no other flag will fix it (see below).

What `natural` does buy outright is weight separation: the Bold/Regular ink ratio goes from 1.1203
to 1.1236. That matters more here than it normally would, because this family's Bold is only one
step above its Regular (JetBrains Light 300 vs Regular 400) -- and it is exactly what `strong` was
spending, at 1.0938.

Measured as the fraction of ink rendered at full saturation rather than smeared into half-grays,
over 9-18 ppem on the Light face; the ink ratio is the same measurement run over both roman faces.
ttfautohint emits a `prep` that branches on rendering mode, and which branch reaches whom is easy
to get backwards: FreeType's default **v40 interpreter emulates ClearType**, so it takes the
*DirectWrite* branch, not the grayscale one. That is why `dw-` is the mode that actually moves
these numbers, and `gray-` is set alongside it only for the legacy v35 interpreter.

These figures were re-measured for the `natural` change. The harness behind the numbers quoted in
commits `34aed65` and `5bbd30c` was never committed, so the absolute values here do not match those
-- the row ordering and the direction of every delta do.

### If it still reads too crisp

Nothing left in ttfautohint's flags will help; the remaining levers each give up something real:

| Lever | What it does | What it costs |
|---|---|---|
| `hinting-limit=N` (needs `hinting-range-max<=N`) | stops hinting above N ppem | measured identical to plain `natural` across 9-18 ppem, so it only changes sizes above the limit |
| `dehint`, or shipping the sources unhinted | pure outline anti-aliasing, macOS-style | gives up the symbol hinting this build exists for, and `validate.py`'s smart-dropout, `fpgm`/`prep` and `TTFA` checks would all have to go |
| `control-instructions` | per-glyph, per-ppem manual fixes | the real foundry lever, and it needs per-glyph visual review rather than a metric |

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
| per-face stem modes | Regular `strong` + Bold `quantized`, tried while `strong` was still in: recovered only +0.06% of the weight contrast while costing Bold a fifth of its crispness gain. |
| `gasp` tuning | Built and installed as a separate family (`{20: 0x07, 65535: 0x0F}` -- no ClearType symmetric smoothing at or below 20 ppem) and compared side by side in a real editor on Windows/DirectWrite, since FreeType ignores `gasp` and the harness here is blind to it. **No visible difference**, so the variant was dropped and `gasp` stays exactly as upstream ships it. |

### Known limits of this tuning

The parameter search is exhausted, but the *quality* ceiling is not:

- **Control instructions are untouched.** ttfautohint's `control_file` allows per-glyph, per-ppem
  manual fixes, which is how a foundry polishes autohinting beyond what flags can reach. That is
  the biggest remaining lever, and it needs per-glyph visual review rather than a metric.
- **Only FreeType grayscale was measured.** DirectWrite, CoreText and subpixel/LCD ClearType were
  not -- they cannot be driven from this pipeline. That gap is part of why the `strong` stem mode
  was reverted on how it actually looked rather than on its numbers, and it is why `natural` should
  be judged the same way: a 2% move on a proxy metric is well inside the range where only daily
  reading can say whether it helped.
- **The measurement harness is not in the repo.** The numbers above are reproducible in principle
  -- render at 9-18 ppem through FreeType and count fully-saturated pixels -- but nothing in the
  pipeline re-runs them, so they age silently.
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
