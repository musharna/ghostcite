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


NESTED_BRACE = r"""
@article{nestedbrace2023,
  author  = {Doe, Jane},
  title   = {The {ATP}-dependent chromatin remodeler},
  journal = {Cell},
  year    = {2023},
  doi     = {10.1/nested},
}
"""


def test_nested_brace_title_not_truncated():
    # A brace-protected acronym inside a title must not truncate the field at
    # the first inner closing brace. Must capture the FULL title text.
    import time

    t0 = time.monotonic()
    c = parse_bibtex(NESTED_BRACE)[0]
    elapsed = time.monotonic() - t0
    assert elapsed < 0.5, f"regex took {elapsed:.3f}s — possible backtracking"
    assert "ATP" in c.claimed_title
    assert "dependent chromatin remodeler" in c.claimed_title
    assert "chromatin remodeler" in c.claimed_title
