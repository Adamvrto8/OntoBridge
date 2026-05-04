from __future__ import annotations

from pathlib import Path

from ontobridge.agents.harvester.protocols import RawDocument
from ontobridge.models.enums import SourceType


class PlainTextReader:
    """Reads .txt files and splits them into paragraph-level RawDocuments."""

    source_type: SourceType = SourceType.POLICY_DOC

    def can_read(self, source: Path | str) -> bool:
        return Path(source).suffix.lower() == ".txt"

    def read(self, source: Path | str) -> list[RawDocument]:
        path = Path(source)
        raw = path.read_text(encoding="utf-8", errors="replace")
        return _paragraphs_to_docs(raw, source_hint=path.name)


def _paragraphs_to_docs(text: str, source_hint: str = "") -> list[RawDocument]:
    """Split text on blank lines; return one RawDocument per non-empty paragraph."""
    docs: list[RawDocument] = []
    current_section: str | None = None

    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        # A short ALL-CAPS or title-case line with no terminal punct → section heading
        first_line = para.splitlines()[0].strip()
        if len(first_line) <= 80 and first_line == first_line.title() and not first_line.endswith("."):
            current_section = first_line
            # If only a heading with no body, skip — the next para inherits the section
            body = "\n".join(para.splitlines()[1:]).strip()
            if body:
                docs.append(RawDocument(text=body, section=current_section))
        else:
            docs.append(RawDocument(text=para, section=current_section))

    return docs
