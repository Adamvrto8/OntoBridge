from __future__ import annotations

from ontobridge.agents.harvester.readers.catalog import CatalogReader
from ontobridge.agents.harvester.readers.docx import DocxReader
from ontobridge.agents.harvester.readers.pdf import PdfReader
from ontobridge.agents.harvester.readers.text import PlainTextReader

__all__ = ["CatalogReader", "DocxReader", "PdfReader", "PlainTextReader"]
