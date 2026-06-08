from ghostcite.compare import normalize_surname, title_similar


def test_fold_diacritics():
    assert normalize_surname("Bürger") == normalize_surname("Burger") == "burger"


def test_strip_case_and_punct():
    assert normalize_surname("O'Brien") == "obrien"
    assert normalize_surname("  van der Berg ") == "vanderberg"


def test_empty_and_none():
    assert normalize_surname("") == ""
    assert normalize_surname(None) == ""


def test_title_similar_true_for_same_title():
    assert (
        title_similar(
            "Integrated Transcriptome and Proteome Analysis",
            "Integrated transcriptome and proteome analysis reveals...",
        )
        is True
    )


def test_title_similar_false_for_different_papers():
    assert (
        title_similar(
            "Auxin response factors in lateral roots",
            "A genome resource for Neocamarosporium betae",
        )
        is False
    )


def test_title_similar_handles_missing():
    assert title_similar(None, "x") is False
    assert title_similar("x", None) is False
