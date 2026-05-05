from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# Default ontology path is resolved relative to the ontobridge project root
# (i.e. the directory containing pyproject.toml). Callers can override.
_DEFAULT_ONTOLOGY = (
    Path(__file__).resolve().parents[3] / "ontology" / "ontobridge_ontology_v0.1.ttl"
)


@dataclass(frozen=True)
class DashboardConfig:
    ontology_path: Path = _DEFAULT_ONTOLOGY
    miro_board_url: str | None = None
    page_title: str = "OntoBridge — Steward Dashboard"
    page_icon: str = "🏦"
    db_path: Path | None = None
    """Path to a SQLite database file for persistent storage.

    When ``None`` (default) the dashboard runs in demo mode using an
    in-memory publisher pre-seeded with sample terms.  Data is lost on
    restart but requires no setup.

    When set to a file path, a ``SqlitePublisher`` is used instead.  The
    database is created automatically on first launch and seeded with sample
    terms if empty.  Data persists across restarts.

    Example::

        DashboardConfig(db_path=Path("ontobridge.db"))
    """
