"""PDF/DOCX manuscript input: extraction, section finding, entry splitting.

The DOCX and PDF fixtures are built by hand here (a zip with a
``word/document.xml``; a one-page uncompressed PDF with a text stream), so the
extractors run against real container formats, not a mocked text. The live
end-to-end on a typeset journal PDF is in ``test_document_live.py``.
"""

from __future__ import annotations

import io
import json
import sys
import zipfile

import pytest

from ghostcite import cli
from ghostcite.parsers import parse, parse_file_bytes
from ghostcite.parsers.document import (
    DocumentInputError,
    extract_docx_text,
    extract_pdf_text,
    extract_text,
    parse_document,
    parse_document_text,
    reference_section,
    split_entries,
)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def make_docx(blocks: list[tuple[str, str]]) -> bytes:
    """``[(kind, text)]`` with kind in {"p", "h", "tbl"} -> DOCX bytes."""
    body = []
    for kind, text in blocks:
        if kind == "tbl":
            body.append(
                f"<w:tbl><w:tr><w:tc><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
            )
            continue
        style = '<w:pPr><w:pStyle w:val="Heading1"/></w:pPr>' if kind == "h" else ""
        # split on "|" to exercise multiple runs + a tab inside one paragraph
        runs = "".join(f"<w:r><w:t>{part}</w:t></w:r>" for part in text.split("|"))
        tab = "<w:r><w:tab/></w:r>" if "|" in text else ""
        body.append(f"<w:p>{style}{runs}{tab}</w:p>")
    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{W}"><w:body>'
        + "".join(body)
        + "</w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", xml)
    return buf.getvalue()


def make_pdf(lines: list[str]) -> bytes:
    """One page, Helvetica, one Tj per line: enough for pypdf's text extractor."""
    ops = ["BT", "/F1 10 Tf", "12 TL", "50 780 Td"]
    for ln in lines:
        esc = ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        ops.append(f"({esc}) Tj T*")
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


# ---------------------------------------------------------------------------
# extraction
# ---------------------------------------------------------------------------


def test_docx_extract_paragraphs_headings_and_tables():
    data = make_docx(
        [
            ("h", "Introduction"),
            ("p", "Body text with|two runs and a tab."),
            ("h", "References"),
            ("p", "Chen, M. (2024). A paper. Plants 13:869."),
            ("tbl", "Cell text"),
        ]
    )
    text = extract_docx_text(data)
    assert text.splitlines() == [
        "## Introduction",
        "Body text withtwo runs and a tab.",  # runs concatenate; the tab lands where the run is
        "## References",
        "Chen, M. (2024). A paper. Plants 13:869.",
        "## (table)",
        "Cell text",
    ]


def test_docx_extract_rejects_non_docx_bytes():
    with pytest.raises(DocumentInputError, match="not a DOCX"):
        extract_docx_text(b"not a zip")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", "application/vnd.oasis.opendocument.text")
    with pytest.raises(DocumentInputError, match="word/document.xml"):
        extract_docx_text(buf.getvalue())


def test_pdf_extract_reads_lines_in_order():
    pdf = make_pdf(
        ["References", "Chen M. 2024. A paper. Plants 13:869.", "Li X. 2023. Another. Nature 1:2."]
    )
    text = extract_pdf_text(pdf)
    assert "Chen M. 2024. A paper. Plants 13:869." in text
    assert text.index("References") < text.index("Chen M.") < text.index("Li X.")


def test_pdf_extract_rejects_garbage():
    with pytest.raises(DocumentInputError, match="cannot read PDF"):
        extract_pdf_text(b"%PDF-1.4\ngarbage")


def test_pdf_extract_names_the_extra_when_pypdf_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "pypdf", None)
    monkeypatch.setitem(sys.modules, "pypdf.errors", None)
    with pytest.raises(DocumentInputError, match=r"pip install 'ghostcite\[pdf\]'"):
        extract_pdf_text(b"%PDF-1.4")
    # positive control: the same call with pypdf present does not raise that
    monkeypatch.delitem(sys.modules, "pypdf")
    monkeypatch.delitem(sys.modules, "pypdf.errors")
    assert "Chen" in extract_pdf_text(make_pdf(["Chen M. 2024. x"]))


def test_extract_text_dispatches_on_suffix_only():
    docx = make_docx([("p", "hello")])
    assert extract_text(docx, "a.DOCX") == "hello"
    with pytest.raises(DocumentInputError, match="not a .pdf or .docx"):
        extract_text(docx, "a.odt")


# ---------------------------------------------------------------------------
# reference section
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "heading",
    [
        "References",
        "REFERENCES",
        "R\nEFERENCES",  # drop cap split across lines by the PDF extractor
        "R E F E R E N C E S",  # letter-spaced small caps
        "7. References",
        "7.2 Reference list",
        "## References",
        "Literature Cited",
        "LITERATURE  CITED",
        "Works cited:",
        "Bibliography",
    ],
)
def test_reference_section_finds_heading_forms(heading):
    text = f"Intro.\nSee references below.\n{heading}\nChen M. 2024. A paper.\n"
    sec = reference_section(text)
    assert sec.found_heading
    assert sec.text.strip() == "Chen M. 2024. A paper."
    # the entry's reported line is its true line in the extracted text
    chen_line = text[: text.index("Chen M.")].count("\n") + 1
    assert parse_document_text(text)[0].source_line == chen_line


def test_reference_section_uses_last_heading_and_stops_at_next():
    text = "References\nnot this one\n## References\nChen M. 2024. x\n## Supplementary\nTable 1 (2020)\n"
    sec = reference_section(text)
    assert sec.text.strip() == "Chen M. 2024. x"


def test_reference_section_without_heading_is_whole_text():
    sec = reference_section("Chen M. 2024. x\nLi X. 2023. y\n")
    assert not sec.found_heading and sec.start_line == 1
    assert sec.text.startswith("Chen M.")
    # "references" in running prose is not a heading
    sec = reference_section("we list references in the appendix\nChen M. 2024. x\n")
    assert not sec.found_heading


# ---------------------------------------------------------------------------
# entry splitting
# ---------------------------------------------------------------------------

WRAPPED = """\
Abdul Aziz H., Hilgen F.J., van Luijk G.M., Sluijs A., Kraus M.J.,
Pares J.M., Gingerich P.D. 2008. Astronomical climate control on
paleosol stacking patterns in the upper Paleocene. Geology 36:
531–534.
van Tuinen M., Hadly E.A. 2004a. Error in estimation of rate and time
inferred from the early amniote fossil record and avian molecular
clocks. J. Mol. Evol. 59:267–276.
Wiens J.J., Kuczynski C.A., Townsend T., Reeder T.W., Mulcahy D.G.,
Sites J.W. 2010. Combining phylogenomics and fossils in higher-
level squamate reptile phylogeny: molecular data change the place-
ment of fossil taxa. Syst. Biol. 59:674–688.
Palaeontol. Electron. 10:11A.
Downloaded from https://academic.oup.com/x by guest on 1 Jan
Warnock R.C.M., Yang Z. 2012. Exploring uncertainty. Biol. Lett.
2011. Not an entry: a year at a line start is not a list number.
"""


def test_split_wrapped_author_year_entries():
    entries = split_entries(WRAPPED, first_line=100)
    assert [(n, e[:22]) for n, e in entries] == [
        (100, "Abdul Aziz H., Hilgen "),
        (104, "van Tuinen M., Hadly E"),
        (107, "Wiens J.J., Kuczynski "),
        (113, "Warnock R.C.M., Yang Z"),
    ]
    # wrapped lines joined with a space; hyphenated words rejoined; footer dropped
    _, wiens = entries[2]
    assert "the placement of fossil taxa" in wiens  # "place-\nment" rejoined
    # A hyphenated compound broken at the margin ("higher-\nlevel") takes the
    # same reading; author, year and DOI never sit on such a break, so the
    # cheaper rule wins over a dictionary.
    assert "higherlevel squamate" in wiens
    assert "Sites J.W. 2010." in wiens  # continuation after a trailing comma
    assert "Downloaded from" not in " ".join(e for _, e in entries)
    # the stray "Palaeontol. Electron. 10:11A." line has no year: not a start
    assert "Palaeontol. Electron. 10:11A." in wiens
    assert "Not an entry" in entries[3][1]


SMALL_CAPS = """\
AYALA, J. A., A. RZHETSKY, and F. J. AYALA. 1998. Origin of the
metazoan phyla. Proc. Natl. Acad. Sci. USA 95:606–611.
BININDA-EMONDS, O., and M. J. SANDERSON. 2001. Scaling of accuracy.
Syst. Biol. 50:565–579.
"""


def test_split_small_caps_surnames():
    entries = split_entries(SMALL_CAPS)
    assert [e[:14] for _, e in entries] == ["AYALA, J. A., ", "BININDA-EMONDS"]


NUMBERED = """\
[1] Chen M, Zhang L. Integrated transcriptome analysis. Plants.
2024;13:869.
[2] Ngou B, et al. Mutual potentiation. Nature. 2021;592:110-115.
[3] Li X. Something. J Hered. 1995;95:200.
"""


def test_split_numbered_list_strips_markers():
    entries = split_entries(NUMBERED)
    assert [e[:10] for _, e in entries] == ["Chen M, Zh", "Ngou B, et", "Li X. Some"]
    assert entries[0][1].endswith("Plants. 2024;13:869.")
    dotted = NUMBERED.replace("[1]", "1.").replace("[2]", "2.").replace("[3]", "3.")
    assert [e[:10] for _, e in split_entries(dotted)] == ["Chen M, Zh", "Ngou B, et", "Li X. Some"]


def test_numbered_branch_needs_a_counting_sequence():
    # three lines that start "N." but do not count up: page numbers, not markers
    text = "Chen M. 2024. x.\n12. 345 pages.\nLi X. 2023. y.\n40. more.\nWu Y. 2022. z.\n7. end.\n"
    entries = split_entries(text)
    assert [e[:6] for _, e in entries] == ["Chen M", "Li X. ", "Wu Y. "]


def test_split_blank_line_separated_apa():
    text = "Barton, N. H., & Hewitt, G. M. (1985). Analysis of hybrid zones.\n\nGrafen, A. (1989). The phylogenetic regression.\n"
    assert [e[:8] for _, e in split_entries(text)] == ["Barton, ", "Grafen, "]


def test_split_nothing_when_no_entry_starts():
    assert split_entries("just prose without any author year shape\nmore prose\n") == []
    assert split_entries("") == []


# ---------------------------------------------------------------------------
# citations
# ---------------------------------------------------------------------------


def test_parse_document_text_builds_citations():
    text = (
        "## References\n"
        "Barton, N. H., & Hewitt, G. M. (1985). Analysis of hybrid zones. Annu. Rev. Ecol. Syst. "
        "16, 113–148. https://doi.org/10.1146/annurev.es.16.110185.000553\n"
        "van der Berg J. (2020). Particles. J. X 1:2.\n"
        "AYALA, J. A. 1998. Small caps. PNAS 95:606.\n"
        "No year here at all.\n"
    )
    cites = parse_document_text(text)
    assert [(c.claimed_first_author, c.claimed_year, c.doi, c.source_line) for c in cites] == [
        ("Barton", 1985, "10.1146/annurev.es.16.110185.000553", 2),
        ("van der Berg", 2020, None, 3),
        ("AYALA", 1998, None, 4),
    ]
    assert all(c.claimed_title is None for c in cites)
    assert cites[0].raw.startswith("Barton, N. H.")


def test_parse_dispatch_document_format_on_text():
    text = "Intro (2020) says things.\nReferences\nChen M. 2024. A paper.\n"
    assert [c.claimed_first_author for c in parse(text, fmt="document")] == ["Chen"]
    # auto keeps treating plain text as markdown (no bullets: nothing)
    assert parse(text) == []


def test_parse_file_bytes_routes_by_suffix():
    docx = make_docx(
        [("h", "References"), ("p", "Chen, M. (2024). A paper."), ("tbl", "Row (2019)")]
    )
    cites = parse_file_bytes(docx, "ms.docx")
    assert [(c.claimed_first_author, c.claimed_year) for c in cites] == [("Chen", 2024)]
    pdf = make_pdf(["REFERENCES", "Chen M. 2024. A paper. Plants 13:869."])
    assert [c.claimed_first_author for c in parse_file_bytes(pdf, "ms.PDF")] == ["Chen"]
    assert parse_document(pdf, "ms.pdf")[0].claimed_year == 2024
    # an explicit text format is honoured even on a document suffix (this tiny
    # PDF is pure ASCII, so it decodes and simply holds no BibTeX entries)
    assert parse_file_bytes(pdf, "ms.pdf", fmt="bibtex") == []
    # bytes that are not text fail loud instead of parsing as an empty file
    with pytest.raises(ValueError, match="not UTF-8 text"):
        parse_file_bytes(b"\xff\xfe\x00", "ms.pdf", fmt="markdown")
    # text files still go through the text parsers
    assert parse_file_bytes(b"10.1234/abc\n", "dois.txt")[0].doi == "10.1234/abc"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_dry_run_on_docx_and_pdf(tmp_path, capsys):
    (tmp_path / "ms.docx").write_bytes(
        make_docx(
            [
                ("h", "References"),
                (
                    "p",
                    "Barton, N. H. (1985). Hybrid zones. https://doi.org/10.1146/annurev.es.16.110185.000553",
                ),
                ("p", "Grafen, A. (1989). The phylogenetic regression."),
            ]
        )
    )
    (tmp_path / "ms.pdf").write_bytes(
        make_pdf(["References", "Chen M. 2024. A paper. Plants 13:869."])
    )
    rc = cli.main([str(tmp_path), "--dry-run", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out == {"dry_run": True, "total": 3, "with_doi": 1, "without_doi": 2}


def test_cli_reports_document_with_no_entries(tmp_path, capsys):
    (tmp_path / "notes.docx").write_bytes(make_docx([("p", "No references in here.")]))
    rc = cli.main([str(tmp_path / "notes.docx"), "--dry-run"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "no reference entries found" in captured.err
    assert "would check 0 entries" in captured.out


def test_cli_bad_document_exits_2(tmp_path, capsys):
    (tmp_path / "broken.docx").write_bytes(b"not a zip at all")
    rc = cli.main([str(tmp_path / "broken.docx"), "--dry-run"])
    assert rc == 2
    assert "not a DOCX" in capsys.readouterr().err
