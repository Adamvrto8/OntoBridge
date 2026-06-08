"""FastAPI entry point.

Do NOT use --reload — FIBO indexing takes 1-3 min at startup and would
re-run on every code change.

Demo mode (in-memory, resets on restart):
    python -m uvicorn api_server:app --host 0.0.0.0 --port 8001

Persistent mode (SQLite, survives restarts):
    $env:DB_PATH="ontobridge.db"; python -m uvicorn api_server:app --host 0.0.0.0 --port 8001  # PowerShell
    DB_PATH=ontobridge.db python -m uvicorn api_server:app --host 0.0.0.0 --port 8001           # Linux/Mac

Bring your own ontology (per-bank deployment):
    $env:ONTOLOGY_PATH="ontology/sample_bank_acme.ttl"; python -m uvicorn api_server:app  # PowerShell
    ONTOLOGY_PATH=ontology/sample_bank_acme.ttl python -m uvicorn api_server:app           # Linux/Mac
Defaults to the bundled retail-banking baseline when unset.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Load secrets from a local .env (gitignored) before anything reads os.environ.
# Existing real env vars take precedence (override=False).
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from ontobridge.api.main import create_app

app = create_app(
    ontology_path=os.environ.get(
        "ONTOLOGY_PATH", "ontology/ontobridge_ontology_v0.1.ttl"
    ),
    db_path=os.environ.get("DB_PATH"),
)
