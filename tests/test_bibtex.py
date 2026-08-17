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


# --- entry delimiting -------------------------------------------------------
# Until 2026-08-17 an entry's END was decided by what FOLLOWED it: the pattern
# required the closing brace to be followed by `@` or end-of-input. Any other
# text between two entries -- a `%` comment, a stray note, a LaTeX line --
# failed that lookahead, so `.*?` ran on to a LATER closing brace and merged two
# entries into one. The count dropped by one and the SECOND entry's fields were
# shadowed by the first's, silently: exit status and the "0 findings" line are
# identical either way, so a dropped citation is indistinguishable from an
# audited one. Found in a 17-entry bibliography that reported 16, where the
# entry it lost was the one the work rested on.

TWO_ENTRIES_HEAD = r"""
@article{first2020,
  author = {Alpha, A.},
  title  = {First},
  year   = {2020},
  doi    = {10.1/first},
}
"""
TWO_ENTRIES_TAIL = r"""
@article{second2021,
  author = {Beta, B.},
  title  = {Second},
  year   = {2021},
  doi    = {10.2/second},
}
"""


def _between(sep: str):
    return TWO_ENTRIES_HEAD + sep + TWO_ENTRIES_TAIL


def test_text_between_entries_does_not_swallow_the_next_entry():
    """The bug is not about `%`. ANY non-@ text between entries triggered it."""
    for sep in (
        "",                       # control: nothing between them
        "% a plain comment\n",
        "%% doubled comment marker\n",
        "some stray prose\n",
        "\n\nnotes to self\n\n",
        "% multi\n% line\n% comment block\n",
        "\\section{Refs}\n",
    ):
        cites = parse_bibtex(_between(sep))
        assert len(cites) == 2, f"separator {sep!r} lost an entry: got {len(cites)}"
        dois = {c.doi for c in cites}
        assert dois == {"10.1/first", "10.2/second"}, f"separator {sep!r} gave {dois}"
        authors = {c.claimed_first_author for c in cites}
        assert authors == {"Alpha", "Beta"}, f"separator {sep!r} gave {authors}"


def test_leading_comment_before_first_entry_still_parses():
    """This case always worked; it is here so a fix cannot trade one for the other."""
    cites = parse_bibtex("% a header comment\n% second line\n" + TWO_ENTRIES_HEAD)
    assert len(cites) == 1
    assert cites[0].doi == "10.1/first"


def test_at_comment_block_is_not_a_citation():
    """`@comment{...}` is BibTeX metadata, not a reference."""
    src = TWO_ENTRIES_HEAD + "@comment{ignore me}\n" + TWO_ENTRIES_TAIL
    cites = parse_bibtex(src)
    assert len(cites) == 2, f"got {len(cites)}"
    assert {c.doi for c in cites} == {"10.1/first", "10.2/second"}


def test_string_and_preamble_are_not_citations():
    src = (
        '@string{jrnl = "Journal of Things"}\n'
        + TWO_ENTRIES_HEAD
        + "@preamble{ \\newcommand{\\x}{y} }\n"
        + TWO_ENTRIES_TAIL
    )
    cites = parse_bibtex(src)
    assert len(cites) == 2, f"got {len(cites)}: {[c.raw for c in cites]}"
