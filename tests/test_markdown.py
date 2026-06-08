from ghostcite.parsers.markdown import parse_markdown

SAMPLE = """\
# References

- **Chen M, Zhang L, Yao Z (2024).** Integrated transcriptome analysis. Plants 13(6):869. https://doi.org/10.3390/plants13060869
- **Ngou B et al. (2021).** Mutual potentiation of plant immunity. Nature.
- not a reference line
"""


def test_parses_bullet_refs():
    cites = parse_markdown(SAMPLE)
    assert len(cites) == 2
    assert cites[0].claimed_first_author == "Chen"
    assert cites[0].claimed_year == 2024
    assert cites[0].doi == "10.3390/plants13060869"


def test_ref_without_doi():
    c = parse_markdown(SAMPLE)[1]
    assert c.claimed_first_author == "Ngou"
    assert c.claimed_year == 2021
    assert c.doi is None
