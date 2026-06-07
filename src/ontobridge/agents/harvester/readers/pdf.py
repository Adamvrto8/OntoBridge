from __future__ import annotations

from pathlib import Path

from ontobridge.agents.harvester.protocols import RawDocument
from ontobridge.agents.harvester.readers.text import _paragraphs_to_docs
from ontobridge.models.enums import SourceType

# pypdf's extract_text() can insert spaces inside words ("nec essary",
# "cooper ation"). We repair these using a spell checker when available:
# two lowercase fragments joined by a single space are merged only when the
# joined form is a real word and the parts are NOT both real words — so
# "nec essary" -> "necessary" but "credit risk" is left untouched.
_SPELL: object = "unset"


def _get_spell():
    global _SPELL
    if _SPELL == "unset":
        try:
            from spellchecker import SpellChecker
            _SPELL = SpellChecker()
        except Exception:
            _SPELL = None
    return _SPELL


def _repair_spacing(text: str) -> str:
    spell = _get_spell()
    if spell is None or not text:
        return text
    out_lines: list[str] = []
    for line in text.split("\n"):
        tokens = line.split()
        if not tokens:
            out_lines.append(line)
            continue
        merged: list[str] = []
        i = 0
        while i < len(tokens):
            cur = tokens[i]
            while (
                i + 1 < len(tokens)
                and cur.isalpha() and cur.islower()
                and tokens[i + 1].isalpha() and tokens[i + 1].islower()
            ):
                cand = cur + tokens[i + 1]
                if spell.known([cand]) and not (
                    spell.known([cur]) and spell.known([tokens[i + 1]])
                ):
                    cur = cand
                    i += 1
                else:
                    break
            merged.append(cur)
            i += 1
        out_lines.append(" ".join(merged))
    return "\n".join(out_lines)


class PdfReader:
    """Reads PDF files page-by-page using pypdf.

    Requires: pip install pypdf>=3.0  (or the [readers] optional dep group)
    """

    source_type: SourceType = SourceType.POLICY_DOC

    def can_read(self, source: Path | str) -> bool:
        return Path(source).suffix.lower() == ".pdf"

    def read(self, source: Path | str) -> list[RawDocument]:
        try:
            from pypdf import PdfReader as _PdfReader
        except ImportError as exc:
            raise ImportError(
                "pypdf is required for PdfReader.\n"
                "Install it with:  pip install pypdf>=3.0"
            ) from exc

        reader = _PdfReader(str(source))
        docs: list[RawDocument] = []
        for page_num, page in enumerate(reader.pages, start=1):
            text = _repair_spacing(page.extract_text() or "")
            for doc in _paragraphs_to_docs(text, source_hint=str(source)):
                doc.page = page_num
                docs.append(doc)
        return docs
