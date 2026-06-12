from ghostcite.crossref import _record_from_message


def test_abstract_is_stripped_of_jats_tags():
    msg = {
        "DOI": "10.1/x",
        "author": [{"family": "Chen"}],
        "title": ["A title"],
        "abstract": "<jats:p>We <jats:italic>show</jats:italic> a result.</jats:p>",
    }
    rec = _record_from_message(msg)
    assert rec.abstract == "We show a result."


def test_abstract_absent_is_none():
    rec = _record_from_message({"DOI": "10.1/x", "title": ["t"]})
    assert rec.abstract is None
