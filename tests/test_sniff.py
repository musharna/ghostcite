from ghostcite.parsers import parse, sniff

BIB = "@article{k,\n author={Li, X},\n year={2024},\n doi={10.1234/a}\n}"
MD = "- **Chen M (2024).** Title. https://doi.org/10.1234/a"
DOIS = "10.3390/plants13060869\n10.1038/s41586-024-00001"


def test_sniff():
    assert sniff(BIB) == "bibtex"
    assert sniff(MD) == "markdown"
    assert sniff(DOIS) == "doi"


def test_parse_dispatches_by_sniff():
    assert parse(BIB)[0].claimed_first_author == "Li"
    assert parse(MD)[0].claimed_first_author == "Chen"
    assert parse(DOIS)[0].doi == "10.3390/plants13060869"


def test_parse_honors_explicit_format():
    # Force DOI mode on markdown → only the DOI is extracted, no author.
    out = parse(MD, fmt="doi")
    assert out[0].claimed_first_author is None and out[0].doi == "10.1234/a"
