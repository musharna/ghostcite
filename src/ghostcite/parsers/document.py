"""Manuscript input: PDF and DOCX reference lists.

The other parsers take a bibliography the author already exported. Most
manuscripts never had one: the reference list lives at the end of a Word file
or a typeset PDF. This module gets from those bytes to ``Citation`` objects in
three steps, each a plain function so it can be tested on its own:

1. ``extract_text`` -- DOCX through the stdlib (``word/document.xml``, one line
   per paragraph); PDF through ``pypdf`` (the optional ``ghostcite[pdf]``
   extra), one line per extracted text line.
2. ``reference_section`` -- the text after the LAST "References" /
   "Bibliography" / "Literature Cited" / "Works Cited" heading. Typeset PDFs
   split a drop-cap heading across lines ("R\\nEFERENCES") and letter-space
   small caps, so the heading pattern allows whitespace between letters. No
   heading: the whole text is scanned and the caller is told so.
3. ``split_entries`` -- one string per reference. A numbered list ("[12]",
   "12.") splits on its markers. Otherwise an entry starts on a line that
   opens with an author (surname then initial or comma), follows a line that
   ended an entry (terminal "." / ")" / a page range) and has a year within
   its first three lines. Wrapped lines are joined; a trailing hyphen followed
   by a lowercase letter is a broken word, not a compound.

What is claimed per entry is what the other parsers claim: first author,
year, and DOI when printed. The title is not delimited (same as the markdown
parser), so DOI-less entries go through CrossRef's bibliographic search on
author + year.
"""

from __future__ import annotations

import re
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from ghostcite.models import Citation
from ghostcite.parsers.doi import clean_doi
from ghostcite.parsers.markdown import _DOI, _FIRST_AUTHOR


class DocumentInputError(ValueError):
    """The document cannot be read as PDF/DOCX (bad bytes or missing extra)."""


# ---------------------------------------------------------------------------
# 1. text extraction
# ---------------------------------------------------------------------------

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def extract_docx_text(data: bytes) -> str:
    """One line per paragraph of ``word/document.xml``. Tabs and line breaks
    inside a paragraph become spaces so a reference stays on one line."""
    try:
        with zipfile.ZipFile(_BytesIO(data)) as zf:
            xml = zf.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as e:
        raise DocumentInputError(f"not a DOCX file (no word/document.xml): {e}") from e
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise DocumentInputError(f"DOCX document.xml is not well-formed XML: {e}") from e
    lines: list[str] = []
    body = root.find(f"{{{_W_NS}}}body")
    blocks = list(body) if body is not None else []
    for block in blocks:
        tag = block.tag.rsplit("}", 1)[-1]
        if tag == "tbl":
            # A table after the reference list is an appendix, not a reference;
            # mark it like a heading so the section stops there. Cell text is
            # kept below it for a reference list that was itself laid out as a
            # table (rare, but seen in theses).
            lines.append("## (table)")
        for para in block.iter(f"{{{_W_NS}}}p") if tag != "p" else [block]:
            lines.append(_docx_paragraph_line(para))
    return "\n".join(lines)


def _docx_paragraph_line(para) -> str:
    if True:
        style = para.find(f"{{{_W_NS}}}pPr/{{{_W_NS}}}pStyle")
        style_id = (style.get(f"{{{_W_NS}}}val") or "") if style is not None else ""
        is_heading = style_id.lower().startswith(("heading", "title"))
        parts: list[str] = []
        for node in para.iter():
            tag = node.tag.rsplit("}", 1)[-1]
            if tag == "t" and node.text:
                parts.append(node.text)
            elif tag in ("tab", "br", "cr"):
                parts.append(" ")
        text = "".join(parts).strip()
        # Word knows which paragraphs are headings; a "## " prefix carries that
        # into the plain text so the reference section can stop at the next one
        # (an appendix, a supplementary table) instead of running to the end.
        return f"## {text}" if is_heading and text else text


def extract_pdf_text(data: bytes) -> str:
    """One line per extracted text line, pages joined by a newline.

    Needs ``pypdf`` (``pip install 'ghostcite[pdf]'``); the error says so
    rather than surfacing an ImportError from deep inside a parser.
    """
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as e:
        raise DocumentInputError(
            "PDF input needs the 'pdf' extra: pip install 'ghostcite[pdf]' "
            "(or pipx inject ghostcite pypdf)"
        ) from e
    try:
        reader = PdfReader(_BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except PdfReadError as e:
        raise DocumentInputError(f"cannot read PDF: {e}") from e
    return "\n".join(pages)


def extract_text(data: bytes, filename: str) -> str:
    """Dispatch on the file suffix; the suffix is the caller's claim about the bytes."""
    lower = filename.lower()
    if lower.endswith(".docx"):
        return extract_docx_text(data)
    if lower.endswith(".pdf"):
        return extract_pdf_text(data)
    raise DocumentInputError(f"{filename}: not a .pdf or .docx file")


def _BytesIO(data: bytes):
    import io

    return io.BytesIO(data)


# ---------------------------------------------------------------------------
# 2. reference section
# ---------------------------------------------------------------------------


def _spaced(word: str) -> str:
    # "references" -> "r\s*e\s*f..." so a drop cap ("R\nEFERENCES") or
    # letter-spaced small caps ("R E F E R E N C E S") still match.
    return r"\s*".join(re.escape(ch) for ch in word)


_HEADINGS = ("references", "reference list", "bibliography", "literature cited", "works cited")
_HEADING_RE = re.compile(
    r"(?im)^[ \t]*(?:#{1,6}[ \t]+)?(?:\d+(?:\.\d+)*\.?[ \t]*)?(?:"
    + "|".join(_spaced(h).replace(r"\ ", r"\s+") for h in _HEADINGS)
    + r")[ \t]*:?[ \t]*$"
)


# A later markdown-style heading ends the section (DOCX headings arrive as
# "## text"; a markdown manuscript has them natively).
_NEXT_HEADING_RE = re.compile(r"(?m)^[ \t]*#{1,6}[ \t]+\S")
# Publisher running footers repeat on every page of a typeset PDF and land in
# the middle of wrapped entries; they are dropped, not treated as section ends.
_FOOTER_RE = re.compile(r"^[ \t]*(?:Downloaded from https?://|by guest on \d)", re.IGNORECASE)


@dataclass
class ReferenceSection:
    text: str
    found_heading: bool
    start_line: int  # 1-based line number in the extracted text where `text` begins


def reference_section(text: str) -> ReferenceSection:
    """Text after the last reference heading, or the whole text when none."""
    last = None
    for m in _HEADING_RE.finditer(text):
        last = m
    if last is None:
        return ReferenceSection(text=text, found_heading=False, start_line=1)
    start = last.end()
    body = text[start:]
    nxt = _NEXT_HEADING_RE.search(body)
    if nxt is not None:
        body = body[: nxt.start()]
    return ReferenceSection(
        text=body, found_heading=True, start_line=text.count("\n", 0, start) + 1
    )


# ---------------------------------------------------------------------------
# 3. entry splitting
# ---------------------------------------------------------------------------

# 1-3 digits: a wrapped entry can put a year at a line start ("2011. Title"),
# and "2011." would otherwise read as marker 2011.
_NUMBERED = re.compile(r"^[ \t]*(?:\[(\d{1,3})\]|(\d{1,3})[.)])[ \t]+(?=\S)")
_YEAR = re.compile(r"\b(?:1[89]|20)\d{2}[a-z]?\b")
# What stands where the year goes, including the undated forms.
_DATED = re.compile(rf"{_YEAR.pattern}|\b(?:in press|forthcoming|n\.\s?d\.)", re.IGNORECASE)
# An entry's first line opens with an author: optional lowercase particles, a
# surname (any case: typeset small caps come out as "AYALA"), then either a
# comma or whitespace and an initial / next name.
_PARTICLES = r"(?:(?i:van|von|de|der|del|della|di|da|dos|du|la|le|den|ter|ten)\s+)*"
_ENTRY_START = re.compile(
    rf"^[ \t]*{_PARTICLES}[A-Z][A-Za-zÀ-ÿ'’¨-]+(?:\s*,\s*|\s+)(?:[A-Z][A-Za-zÀ-ÿ'’.-]*|&)"
)
# The previous line ended an entry: sentence-terminal punctuation, a closing
# paren/bracket, a page range or a bare page/volume number, a DOI or URL.
_ENTRY_END = re.compile(r"(?:[.)\]]|\d+[–-]\d+\.?|:\d+[A-Za-z]?\.?|\d\.?|/\S+)\s*$")

# A byline still in progress at the line break: "... R. GUPTA, A." / "... and".
_MID_BYLINE = re.compile(r"(?:,\s*(?:[A-Z]\s*\.?)?|\band|&)\s*$")


def _borrows_year(line: str, following: list[str]) -> bool:
    """A yearless author-shaped line that is the TAIL of the entry above, not a
    start: it ends the way an entry ends ("Peabody Mus. Nat. Hist. 52:3-105.",
    "Cambridge University Press, New York.") and an entry start follows it. Its
    only year is the next entry's. A byline line ends mid-byline instead.
    """
    if _YEAR.search(line) or _MID_BYLINE.search(line) or not _ENTRY_END.search(line):
        return False
    nxt = next((x for x in following if x.strip()), "")
    return bool(_ENTRY_START.match(nxt))


def _is_numbered_list(lines: list[str], numbered: list[int]) -> bool:
    """A Vancouver-style list: at least three markers, counting up from 1 or 2.

    Page ranges ("12. 345-350") and stray numerals never count up in order,
    so the sequence test is what separates a real list from noise.
    """
    if len(numbered) < 3:
        return False
    values: list[int] = []
    for i in numbered:
        m = _NUMBERED.match(lines[i])
        assert m is not None
        values.append(int(m.group(1) or m.group(2)))
    if values[0] > 2:
        return False
    consecutive = sum(1 for a, b in zip(values, values[1:]) if b == a + 1)
    return consecutive >= 0.8 * (len(values) - 1)


def _join_wrapped(lines: Iterable[str]) -> str:
    out = ""
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if not out:
            out = ln
        elif out.endswith("-") and ln[:1].islower():
            out = out[:-1] + ln  # hyphenated word broken at the margin
        else:
            out = out + " " + ln
    return out


def split_entries(section: str, *, first_line: int = 1) -> list[tuple[int, str]]:
    """``[(line_number, entry_text), ...]`` for one reference section."""
    # Footer lines are blanked, not dropped, so reported line numbers stay true.
    raw_lines = ["" if _FOOTER_RE.match(ln) else ln for ln in section.splitlines()]
    numbered = [i for i, ln in enumerate(raw_lines) if _NUMBERED.match(ln)]
    starts: list[int]
    if _is_numbered_list(raw_lines, numbered):
        starts = numbered
    else:
        starts = []
        prev_ended = True
        # An author-year entry cannot end before its own year has appeared: a
        # byline wrapped after an initial ("... R. GUPTA, A." / "LAPEDES, B. H. ...")
        # otherwise looks like a finished entry followed by a new one.
        dated = True
        for i, ln in enumerate(raw_lines):
            if not ln.strip():
                prev_ended = dated = True
                continue
            # A byline carries a comma or an initial's period; a running head neither.
            if prev_ended and dated and _ENTRY_START.match(ln) and re.search(r"[,.]", ln):
                window = " ".join(x.strip() for x in raw_lines[i : i + 3])
                if _YEAR.search(window) and not _borrows_year(ln, raw_lines[i + 1 : i + 3]):
                    starts.append(i)
                    dated = False
            dated = dated or bool(_DATED.search(ln))
            prev_ended = bool(_ENTRY_END.search(ln))
    if not starts:
        return []
    entries: list[tuple[int, str]] = []
    for n, s in enumerate(starts):
        e = starts[n + 1] if n + 1 < len(starts) else len(raw_lines)
        chunk = raw_lines[s:e]
        if starts is numbered:
            chunk = [_NUMBERED.sub("", chunk[0], count=1), *chunk[1:]]
        text = _join_wrapped(chunk)
        if text:
            entries.append((first_line + s, text))
    return entries


def _citation_from_entry(entry: str, line: int) -> Citation | None:
    ym = _YEAR.search(entry)
    if not ym:
        return None
    author_m = _FIRST_AUTHOR.match(entry)
    doi_m = _DOI.search(entry)
    return Citation(
        raw=entry,
        source_line=line,
        doi=clean_doi(doi_m.group(1)) if doi_m else None,
        claimed_first_author=author_m.group(1) if author_m else None,
        claimed_year=int(ym.group(0)[:4]),
        claimed_title=None,
    )


def parse_document_text(text: str) -> list[Citation]:
    """Reference list of an already-extracted manuscript text."""
    sec = reference_section(text)
    cites: list[Citation] = []
    for line, entry in split_entries(sec.text, first_line=sec.start_line):
        c = _citation_from_entry(entry, line)
        if c is not None:
            cites.append(c)
    return cites


def parse_document(data: bytes, filename: str) -> list[Citation]:
    """PDF/DOCX bytes -> citations. Raises ``DocumentInputError`` on bad input."""
    return parse_document_text(extract_text(data, filename))
