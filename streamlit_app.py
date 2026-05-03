"""Streamlit entry point. Run with:

    streamlit run streamlit_app.py

If the package is not installed (pip install -e .), this script also adds
`src/` to sys.path so a fresh checkout works out of the box.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ontobridge.dashboard.app import main

main()
