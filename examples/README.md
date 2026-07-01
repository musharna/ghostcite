# Examples

Sample inputs for the three formats `ghostcite` accepts, plus the demo-card
generator used in the project README.

| File               | Format                  | Notes                                                            |
| ------------------ | ----------------------- | ---------------------------------------------------------------- |
| `refs.bib`         | BibTeX                  | 3 entries — one ghost citation, two clean.                       |
| `refs.md`          | Markdown reference list | Same three references in `- **Author (YYYY).** … DOI` form.      |
| `dois.txt`         | Bare DOI list           | Lookup + retraction sweep only (no claimed author/year).         |
| `gen_demo_card.py` | —                       | Pillow generator for `assets/demo.png` (needs `ghostcite[viz]`). |

The first entry in `refs.bib` / `refs.md` is the real ghost case: it cites
**Li (2024)** for DOI `10.3390/plants13060869`, but CrossRef says that DOI is
actually **Chen (2024)**. The other two entries (AlphaFold, OrthoFinder) are
correctly attributed and stay silent.

## Captured output

`ghostcite examples/refs.bib` (requires network — hits CrossRef):

```text
ghostcite: 3 entries, 3 with DOIs
  retractions: CrossRef live
  ✗ A  L1  Li (2024)  →  DOI resolves to Chen (2024) — possibly wrong DOI  [10.3390/plants13060869]
  1 A
```

Exit code `1` (a Tier A author-mismatch is present). `examples/refs.md` produces
the same finding at line `L3`.

`ghostcite examples/dois.txt` resolves each DOI and runs the retraction sweep;
with no claimed author/year there is nothing to mismatch, so it reports clean:

```text
ghostcite: 3 entries, 3 with DOIs
  retractions: CrossRef live
  0 findings — clean
```

(Exit code `0`.)

## Regenerating the demo card

```bash
pip install "ghostcite[viz]"   # or: pip install pillow
python3 examples/gen_demo_card.py   # writes examples/assets/demo.png
```
