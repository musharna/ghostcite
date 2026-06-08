from ghostcite.parsers.bibtex import parse_bibtex

SAMPLE = r"""
@article{chen2024,
  author  = {Chen, Min and Zhang, Lei and Yao, Z.},
  title   = {Integrated Transcriptome and Proteome Analysis},
  journal = {Plants},
  year    = {2024},
  doi     = {10.3390/plants13060869},
}

@article{nodoi2021,
  author = {Ngou, B.},
  title  = {Mutual potentiation of plant immunity},
  year   = {2021},
}
"""


def test_parses_fields():
    cites = parse_bibtex(SAMPLE)
    assert len(cites) == 2
    c = cites[0]
    assert c.claimed_first_author == "Chen"
    assert c.claimed_year == 2024
    assert c.doi == "10.3390/plants13060869"
    assert "Integrated Transcriptome" in c.claimed_title


def test_entry_without_doi_has_none():
    c = parse_bibtex(SAMPLE)[1]
    assert c.doi is None
    assert c.claimed_first_author == "Ngou"
    assert c.claimed_year == 2021
