from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from ontobridge.agents.harvester.protocols import RawDocument
from ontobridge.models.enums import SourceType


class CatalogReader:
    """Reads a Unity Catalog metadata export (JSON or CSV) as RawDocuments.

    Each row/entry that has both a ``name`` and a ``description`` field becomes
    one RawDocument.  The ``name`` is stored in ``metadata["catalog_name"]`` so
    the PatternTermExtractor can lift it as the candidate label.

    Expected JSON format (list of objects):
        [{"name": "retail_customer", "description": "...", "schema": "retail"}, ...]

    Expected CSV format (header row required):
        name,description,schema,owner
        retail_customer,A natural person who ...,retail,alice

    When the real Databricks Unity Catalog SDK is available, subclass or replace
    ``read()`` to call the SDK and convert each ``CatalogTable`` / ``ColumnInfo``
    to a dict with ``name`` and ``description`` keys — the rest of the pipeline
    stays unchanged.
    """

    source_type: SourceType = SourceType.CATALOG

    #: Fields tried in order when looking for the term label
    LABEL_FIELDS: tuple[str, ...] = ("name", "term_name", "label", "title")
    #: Fields tried in order when looking for the definition text
    DEFINITION_FIELDS: tuple[str, ...] = (
        "description", "definition", "comment", "business_description"
    )

    def can_read(self, source: Path | str) -> bool:
        return Path(source).suffix.lower() in {".json", ".csv"}

    def read(self, source: Path | str) -> list[RawDocument]:
        path = Path(source)
        suffix = path.suffix.lower()
        if suffix == ".json":
            rows = self._read_json(path)
        elif suffix == ".csv":
            rows = self._read_csv(path)
        else:
            raise ValueError(f"CatalogReader cannot handle extension: {suffix!r}")
        return [doc for row in rows if (doc := self._row_to_doc(row)) is not None]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _read_json(self, path: Path) -> list[dict[str, Any]]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "items" in data:
            return data["items"]
        return [data]

    def _read_csv(self, path: Path) -> list[dict[str, Any]]:
        with path.open(encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))

    def _row_to_doc(self, row: dict[str, Any]) -> RawDocument | None:
        label = self._pick(row, self.LABEL_FIELDS)
        definition = self._pick(row, self.DEFINITION_FIELDS)
        if not label or not definition or len(definition.split()) < 5:
            return None
        # Emit as "label: definition" so PatternTermExtractor parses it cleanly
        text = f"{label}: {definition}"
        section = row.get("schema") or row.get("catalog") or row.get("domain") or None
        return RawDocument(
            text=text,
            section=str(section) if section else None,
            metadata={k: str(v) for k, v in row.items() if v},
        )

    @staticmethod
    def _pick(row: dict[str, Any], candidates: tuple[str, ...]) -> str:
        for key in candidates:
            val = row.get(key, "")
            if val and str(val).strip():
                return str(val).strip()
        # case-insensitive fallback
        lower = {k.lower(): v for k, v in row.items()}
        for key in candidates:
            val = lower.get(key, "")
            if val and str(val).strip():
                return str(val).strip()
        return ""
