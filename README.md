# rnetonet-ttf

A variable coding font, rebranded from **Cascadia Mono** and shifted lighter: Regular sits exactly
halfway between Cascadia's Light and its SemiLight, and Bold is SemiLight itself. No programming
ligatures — `->`, `!=` and `===` stay as the characters they are.

```
rnetonet/
  sources/              upstream Cascadia Mono 2407.024 (build inputs)
  rnetonet-Roman.ttf    rnetonet-Italic.ttf
```

Two files, both variable on `wght` 400–700 with exactly two named instances — Regular at 400 and
Bold at 700 — and everything in between available to anything that can set a variation axis. Bold
carries 1.1124× the ink of Regular: a deliberately light bold.

Install: the two `.ttf` files in `rnetonet/` are the deliverable.

## Building

```sh
python pipeline/build.py       # cut + relabel + rebrand
python pipeline/validate.py    # 159 checks; non-zero exit on any failure
```

Nothing is redrawn and nothing is re-hinted — the outlines, the TrueType hinting and the layout
tables come from upstream untouched. The build cuts the weight axis down to the 325–350 span,
relabels it 400–700 so the OS reads a Regular and a Bold, and rebrands the metadata. It is
byte-reproducible.

See [`pipeline/README.md`](pipeline/README.md) for how the cut works, what it preserves, what it
necessarily moves, and what the validator proves.

Cascadia is © Microsoft Corporation under an SIL OFL 1.1-based licence, which travels with these
files in nameIDs 0, 13 and 14 along with the original author and vendor credits.
