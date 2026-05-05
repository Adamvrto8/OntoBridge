"""Streamlit entry point. Run with:

    streamlit run streamlit_app.py

If the package is not installed (pip install -e .), this script also adds
`src/` to sys.path so a fresh checkout works out of the box.

Storage modes
-------------
Demo (default) — in-memory publisher, seeded on every restart:

    streamlit run streamlit_app.py

Persistent — SQLite publisher, data survives restarts:

    streamlit run streamlit_app.py -- --db ontobridge.db

Pass any filename; the file is created on first launch.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ontobridge.dashboard.app import main
from ontobridge.dashboard.config import DashboardConfig

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--db", default=None, help="Path to SQLite database file")
args, _ = parser.parse_known_args()

cfg = DashboardConfig(db_path=Path(args.db) if args.db else None)
main(cfg)
