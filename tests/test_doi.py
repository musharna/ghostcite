from ghostcite.parsers.doi import parse_doi_list

SAMPLE = """\
10.3390/plants13060869
doi:10.1038/s41586-024-00001
https://doi.org/10.1093/bib/bbx115
# a comment line
not-a-doi
"""


def test_extracts_dois_only():
    cites = parse_doi_list(SAMPLE)
    dois = [c.doi for c in cites]
    assert dois == [
        "10.3390/plants13060869",
        "10.1038/s41586-024-00001",
        "10.1093/bib/bbx115",
    ]
    assert all(c.claimed_first_author is None for c in cites)


def test_balanced_parens_doi_not_truncated():
    # Old Elsevier/Lancet S-DOIs carry balanced parens and must survive intact.
    text = "10.1016/s0140-6736(97)11096-0\n"
    dois = [c.doi for c in parse_doi_list(text)]
    assert dois == ["10.1016/s0140-6736(97)11096-0"]


def test_unbalanced_trailing_paren_stripped():
    # A DOI wrapped in prose parens: the trailing unbalanced ")" must be trimmed.
    text = "(10.3390/plants13060869)\n"
    dois = [c.doi for c in parse_doi_list(text)]
    assert dois == ["10.3390/plants13060869"]


def test_trailing_period_stripped():
    text = "10.1234/foo.\n"
    dois = [c.doi for c in parse_doi_list(text)]
    assert dois == ["10.1234/foo"]


def test_short_prefix_is_not_a_doi():
    # Real DOI registrant prefixes are always >= 4 digits. A 3-digit prefix
    # like "10.5/x" is noise and must not be extracted, while genuine
    # 4-digit-prefix DOIs still are.
    text = "10.5/x\n10.3390/plants13060869\n"
    dois = [c.doi for c in parse_doi_list(text)]
    assert dois == ["10.3390/plants13060869"]
