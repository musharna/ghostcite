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
        "",  # control: nothing between them
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


# --- cost -------------------------------------------------------------------
# Until 2026-09-25 each entry's line number was `text[:start].count("\n")`: a
# slice and a scan from the top of the file for every entry, so parsing was
# quadratic in the number of entries (measured: 1,000 entries 46 ms, 4,000 0.61 s,
# 16,000 10.5 s). The only cost check was the elapsed-time bound above, on one
# five-line entry, which a whole-file rescan passes by construction.
#
# This counts characters instead of seconds: every slice or index the parser
# takes of the input, and every range it hands to str.count, is tallied, so the
# total is the same on every run and on every machine. The regex engine reads
# the string directly and is not counted -- this gate covers the Python-level
# scans, not backtracking.


class _CountingStr(str):
    touched = 0

    def __getitem__(self, key):  # type: ignore[override]
        out = str.__getitem__(self, key)
        type(self).touched += len(out)
        return out

    def count(self, sub, start=None, end=None):  # type: ignore[override]
        s, e, _ = slice(start, end).indices(len(self))
        type(self).touched += max(e - s, 0)
        return str.count(self, sub, start, end)


def _bib_of(n: int) -> str:
    return "".join(
        f"@article{{k{i},\n  author = {{Alpha, A.}},\n  title = {{T {i}}},\n"
        f"  year = {{2020}},\n  doi = {{10.1/x{i}}},\n}}\n\n"
        for i in range(n)
    )


def _touched(text: str) -> tuple[int, list]:
    _CountingStr.touched = 0
    cites = parse_bibtex(_CountingStr(text))
    return _CountingStr.touched, cites


def test_parsing_reads_each_character_a_bounded_number_of_times():
    small, big = _bib_of(100), _bib_of(400)
    t_small, c_small = _touched(small)
    t_big, c_big = _touched(big)

    # The requested workload ran, and line numbers are still right: entry i
    # starts on line 7*i + 1.
    assert len(c_small) == 100 and len(c_big) == 400
    assert [c.source_line for c in c_big] == [7 * i + 1 for i in range(400)]

    # Positive control: the counter sees the parser at all -- matching braces
    # reads every character of every entry, so it cannot count less than that.
    assert t_big >= len(big), f"counted {t_big} of {len(big)} chars; counter is blind"

    # Linear: a bounded number of reads per input character, at both sizes.
    assert t_small <= 4 * len(small), f"{t_small} reads for {len(small)} chars"
    assert t_big <= 4 * len(big), f"{t_big} reads for {len(big)} chars"
