# rnetonet-ttf

Two variable coding fonts, rebranded from **Cascadia** and shifted one step lighter — Cascadia's
Light ships as Regular, its SemiLight as Bold.

| family | from | ligatures |
|---|---|---|
| `rnetonetcode` | Cascadia Code | yes — `-> => != === <=>` … |
| `rnetonetmono` | Cascadia Mono | no |

Each family is two files: `-Roman.ttf` and `-Italic.ttf`, both variable on `wght` 400–700 with
exactly two named instances — Regular at 400 and Bold at 700 — and everything in between
available to anything that can set a variation axis.

```
rnetonet/
  sources/              upstream Cascadia 2407.024 (build inputs)
  rnetonetcode-Roman.ttf   rnetonetcode-Italic.ttf
  rnetonetmono-Roman.ttf   rnetonetmono-Italic.ttf
```

Install: the four `.ttf` files in `rnetonet/` are the deliverable. Pick one family; both installed
at once is fine, they are separate families with identical metrics.

## Building

```sh
python pipeline/build.py       # cut + relabel + rebrand
python pipeline/validate.py    # 306 checks; non-zero exit on any failure
```

Nothing is redrawn and nothing is re-hinted — the outlines, the TrueType hinting and the layout
tables come from upstream untouched. The build cuts the weight axis down to Cascadia's
Light..SemiLight span, relabels it 400–700 so the OS reads a Regular and a Bold, and rebrands the
metadata. It is byte-reproducible.

See [`pipeline/README.md`](pipeline/README.md) for how the cut works, what it preserves, what it
necessarily moves, and what the validator proves.

Cascadia is © Microsoft Corporation under an SIL OFL 1.1-based licence, which travels with these
files in nameIDs 0, 13 and 14 along with the original author and vendor credits.
