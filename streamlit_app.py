"""Streamlit entry point. Run with:

    streamlit run streamlit_app.py

If the package is not installed (pip install -e .), this script also adds
`src/` to sys.path so a fresh checkout works out of the box.

Storage modes
-------------
Demo (default) — in-memory publisher, seeded on every restart:

    python -m streamlit run streamlit_app.py

Persistent — SQLite publisher, data survives restarts:

    python -m streamlit run streamlit_app.py -- --db ontobridge.db

Miro board embed:

    python -m streamlit run streamlit_app.py -- --miro "https://miro.com/app/live-embed/YOUR_BOARD_ID/"

Both flags can be combined:

    python -m streamlit run streamlit_app.py -- --db ontobridge.db --miro "https://miro.com/app/live-embed/YOUR_BOARD_ID/"
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
parser.add_argument("--miro", default=None, help="Miro board live-embed URL")
args, _ = parser.parse_known_args()

cfg = DashboardConfig(
    db_path=Path(args.db) if args.db else None,
    **( {"miro_board_url": args.miro} if args.miro else {} ),
)
main(cfg)
