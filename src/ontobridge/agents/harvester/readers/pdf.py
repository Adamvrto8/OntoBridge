from __future__ import annotations

from pathlib import Path

from ontobridge.agents.harvester.protocols import RawDocument
from ontobridge.agents.harvester.readers.text import _paragraphs_to_docs
from ontobridge.models.enums import SourceType


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
            text = page.extract_text() or ""
            for doc in _paragraphs_to_docs(text, source_hint=str(source)):
                doc.page = page_num
                docs.append(doc)
        return docs
