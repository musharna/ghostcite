from ghostcite.compare import normalize_surname


def test_fold_diacritics():
    assert normalize_surname("Bürger") == normalize_surname("Burger") == "burger"


def test_strip_case_and_punct():
    assert normalize_surname("O'Brien") == "obrien"
    assert normalize_surname("  van der Berg ") == "vanderberg"


def test_empty_and_none():
    assert normalize_surname("") == ""
    assert normalize_surname(None) == ""
