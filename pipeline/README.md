# rnetonet build pipeline

Two scripts that reproduce and verify the `rnetonet` font family from its upstream sources.
The family is a rebrand of **JetBrains Mono**, shifted one step lighter: JetBrains Mono's Light
ships as `rnetonet`'s Regular, and its Regular ships as `rnetonet`'s Bold.

The sources are already static, so nothing is instanced or interpolated and **no outline is ever
redrawn**. The build does two things: re-hints at stock ttfautohint settings, plus a latin fallback
script (so the symbol glyphs get hinted too) and one control instruction that nudges the standard
stem width three units up, and rebrands the metadata. `validate.py` proves the scope by comparing every glyph point coordinate against the
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
| `cvt ` | re-hinted -- gains entries from the `width 74` control instruction |
| `TTFA` | **added** by ttfautohint -- records every parameter used, so the hinting is auditable |
| `name`  | rebranded (see below), plus ttfautohint's version stamp in nameID 5 |
| `OS/2`  | `usWeightClass`, `fsSelection` style bits (+ `USE_TYPO_METRICS`, `WWS`) |
| `head`  | `macStyle` style bits |
| `STAT`  | **added** -- the sources ship none, and a RIBBI family should declare its axis positions |

Everything else passes through byte for byte: layout (`GSUB`/`GPOS`/`GDEF`), `cmap`, `hmtx`,
`hhea`, `post` and `gasp`. To keep that literally true the script probes the layout tables
on a throwaway font handle -- reading `GSUB` through the font it saves would decompile it, and
fontTools would then repack it into different (though equivalent) bytes.

Vertical metrics (typo 1020/-300/0, win 1020/300, upem 1000) are identical across all four faces
and are kept exactly as shipped, so line height is stable across the family.

## Hinting

Upstream JetBrains Mono 2.304 is hinted with **stock ttfautohint defaults**. That is verified
rather than assumed: re-running ttfautohint with no options at all reproduces its `fpgm`, `prep`,
`cvt ` and `glyf` byte for byte -- and it still does with the newer ttfautohint used here
(1.8.4.16-eb64, against the 1.8.4.7-5d5b stamped into the sources). Two things depart from that:
one default that is wrong for a coding font, and one control instruction that is a stated
preference rather than a fix.

| Parameter | Default | Ours | Why |
|---|---|---|---|
| `fallback-script` | `none` | `latn` | `none` means every glyph outside a recognised script gets **no hinting at all** -- here that is 128 box-drawing glyphs, 32 block elements, 21 arrows, 62 math symbols and 43 geometric shapes: exactly what a terminal draws TUI borders, tables, tree views and progress bars with. Affects symbols only. |
| `control-instructions` | none | `* dflt width 74` | Standard stem width, three units above the 71 ttfautohint measures from the outlines. +2.1% crispness, +0.9% ink. A preference, not a fix -- see below. |
| `TTFA-info` | off | on | Writes the `TTFA` table so a built font states how it was hinted. Not a hinting parameter -- it is what `validate.py` reads to prove the config has not drifted. |
| *stem width modes* | quantized / strong / quantized | *unchanged* | Moved to `strong` in `34aed65` and to `natural` in `ed31a38`; both reverted. See below. |

So the shipped hinting is `ttfautohint --fallback-script=latn` plus a one-line control file
containing `* dflt width 74`. Re-hinting is therefore a no-op on everything ttfautohint recognises a script
for -- worth knowing before reaching for a version bump: a newer ttfautohint does not change this
font.

Scope, checked glyph by glyph rather than asserted: **1215 of 1743 glyphs keep upstream's
instruction stream byte for byte.** The 528 that change are box drawing (128), technical (105),
math (105), other symbols (48), arrows (34), block elements (32), geometric shapes (28), plus the
letterlike math alphanumerics (double-struck CHNPQRZ, script l), 12 math brackets, ceilings and
floors, one Gujarati digit and 8 unencoded glyphs. **No Latin letter, digit or ASCII punctuation
mark moves** -- which is the precise version of the claim this README used to make more loosely.

### The stem-width modes: both ends tried, both reverted

The mode is a three-position switch, and this family has now sat in all three positions:

| mode | effect | symbols | letters + digits | Bold/Regular ink ratio |
|---|---|---|---|---|
| `natural` | no rounding at all, softest -- `ed31a38`, reverted | 0.2978 | 0.0786 | 1.1236 |
| `quantized` | **shipped**; ttfautohint's default, identical to upstream | 0.3041 | 0.0800 | 1.1203 |
| `strong` | stems snapped onto whole pixels -- `34aed65`, reverted | 0.3819 | 0.1059 | 1.0938 |

`strong` measured far crisper and **read brittle**. `natural` measured -1.7% on letters and was
**not noticeable in daily use** -- which is the actual finding, and the reason the switch is now
considered spent: one step is too hard, the other is indistinguishable. Nothing useful lives in its
soft half.

Measured as the fraction of ink rendered at full saturation rather than smeared into half-grays,
over 9-18 ppem on the Light face; the ink ratio is the same measurement over both roman faces.
FreeType's default **v40 interpreter emulates ClearType**, so it takes the *DirectWrite* branch,
not the grayscale one -- which is why `dw-` is the mode that moves these numbers.

### The fine dial: control-instruction stem width, and why 74 ships

The mode is coarse, but the standard stem width underneath it is just a number, and control
instructions can set it directly. This is the dial the family ended up on, after both stem width
*modes* were tried and reverted:

```
control_buffer="* dflt width N\n"         # N in font units
```

`latn dflt width N` is not a way to spare the symbols, which is the obvious guess and wrong:
`fallback-script` is `latn`, so the symbol glyphs are hinted *as* latin and take the same
width. Measured identical to `* dflt` on letters and symbols alike -- at width 76, 15
box-drawing glyphs change under either form.

ttfautohint auto-detects **71** for JetBrains Mono Light. That is verified, not guessed: `width 71`
renders identically to leaving it auto -- same `glyf` bytes, same measurements to four decimals.
Measured on letters and digits, 9-18 ppem, against that baseline:

| width | crispness | ink | reads as |
|---|---|---|---|
| 66-69 | -12% | -1.5% | a cliff, not a nudge |
| 70 | -3.9% | -0.3% | a little softer |
| 71 | baseline | baseline | auto -- what ttfautohint measures from the outlines |
| **74** | **+2.1%** | **+0.9%** | **shipped** -- the smallest perceptible step up |
| 75-77 | +1.9 to +2.7% | +1.3 to +1.9% | a little crisper |
| 78-80 | +3.7 to +4.0% | +2.5% | noticeably crisper |
| 90+ | +14% and up | +5% and up | back in `strong` territory |

Two caveats. It is steppy rather than smooth -- quantized mode snaps to a set of widths, so 72 and
73 measure slightly *below* 71 rather than above -- and it moves weight as well as crispness, about
+0.3% ink per unit, which on a Light-based family is not nothing.

**The case against shipping any width, recorded because it was argued and overruled rather than
missed.** 71 is not a default; it is a *measurement of this typeface*, derived by ttfautohint from
the stems of the standard characters as drawn. Overriding it to 74 tells the hinter the stems are
thicker than they are, and the +0.9% ink says the rest: at 13-17 ppem the font renders slightly
heavier than JetBrains Mono Light actually is. On a family whose whole premise is being one step
light (JB Light as Regular), that partly argues with itself, and the honest lever for weight is the
source weight rather than the hint. 74 was chosen anyway, deliberately: it is the smallest step
that reads, +0.9% ink is close to nothing, and the alternative was shipping a font its owner finds
a shade soft. 78-80 were rejected on exactly this ground, since there the weight gain is visible.

**It also costs a guarantee.** Control instructions add `cvt ` entries, so `cvt ` is no longer
byte-identical to the source. It moved out of `validate.py`'s `PRESERVED` set into the re-hinted
one -- a deliberate, recorded widening of the build's scope, not a silenced check. The width itself
is pinned in `EXPECTED_TTFA_CONTROL` and negative-tested: building at width 76 fails the gate on
that exact assertion.

Rejected after measuring, not by taste -- recorded so none of it gets retried on a hunch:

| Rejected | Why |
|---|---|
| `x-height-snapping-exceptions=-` | -5.5% crispness and -3.7% ink, the largest move still available while staying hinted. Built as a side-by-side family (`rnetonetsoft`) and read in place: **no real improvement**, and it costs a pixel of x-height at 13/15/17 ppem. |
| `increase-x-height` | A threshold, not a dial: 0/10/12 all measure -6.0%, and 18/24/32 all measure identical to the default 14. Nothing usable in between. |
| `hinting-range-min=14` | A no-op -- below range-min ttfautohint reuses the smallest hint set rather than dropping hinting. |
| `hinting-limit=N` | Not a dial but a cliff: hinting stops entirely above N ppem, so two adjacent sizes render on different principles. |
| `dehint` | Gives up the symbol hinting this build exists for. Also not measurable with the crispness proxy -- see the limits below. |
| `hint-composites` | Identical metrics even on composite glyphs (accented letters, and the 27 composite ligature glyphs), and +53KB a face. Composites inherit their components' hinting, which is already correct. |
| `adjust-subglyphs` | Accent separation fell 0.865 -> 0.816, and +95KB a face. |
| `x-height-snapping-exceptions=6-16` | +1% crispness, but accent separation fell to 0.812. (Measured during the `strong` era with a harness that no longer exists; the `-` row above is the current number.) |
| `windows-compatibility` | Identical metrics, and it would rewrite the `usWin` metrics the family deliberately keeps as shipped. |
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
  not -- they cannot be driven from this pipeline. That gap is why every setting here was decided
  by reading in a real editor for a day, with the numbers used only to rank what was worth trying:
  `strong` and `natural` both measured cleanly and both lost on how they actually looked.
- **The metric is a proxy, and it breaks across the hinted/unhinted line.** "Fraction of
  fully-saturated ink" tracks crispness within one hinting family. A dehinted build measures
  *higher* (0.1294) than any hinted one, because at that point it is measuring accidental grid
  alignment, not sharpness. Do not compare across that line.
- **The measurement harness is not in the repo.** The numbers above are reproducible in principle
  -- render at 9-18 ppem through FreeType and count fully-saturated pixels -- but nothing in the
  pipeline re-runs them, so they age silently.
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
TTFA table claim `fallback-script=none`, building at stem width 76 instead of 74, leaving the
family name as JetBrains Mono, smuggling a NUL into nameID 3, shifting `sTypoAscender`, dropping a
stylistic-set label) makes the run fail -- each caught by the specific check meant to catch it.

### Requirements

`fonttools`, `ttfautohint-py`, `opentype-sanitizer` (`ots`), `fontbakery`.
