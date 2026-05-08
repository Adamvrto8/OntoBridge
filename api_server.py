"""FastAPI entry point. Run with:

    uvicorn api_server:app --reload

Storage modes
-------------
Demo (default) — in-memory, resets on restart:

    uvicorn api_server:app --reload

Persistent — SQLite, survives restarts:

    DB_PATH=ontobridge.db uvicorn api_server:app --reload   # Linux/Mac
    $env:DB_PATH="ontobridge.db"; uvicorn api_server:app --reload  # PowerShell
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ontobridge.api.main import create_app

app = create_app(
    ontology_path="ontology/ontobridge_ontology_v0.1.ttl",
    db_path=os.environ.get("DB_PATH"),
)
