from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from ontobridge.dashboard.context import DashboardContext


def render_miro(ctx: DashboardContext) -> None:
    st.title("Miro Knowledge Graph")
    st.caption(
        "Steward review artefact — taxonomy + semantic relation visualisation. "
        "See the project proposal § Miro Visualisation Requirements."
    )

    url = ctx.config.miro_board_url
    if url:
        components.iframe(url, height=600, scrolling=True)
        st.caption(f"Embedded board: {url}")
    else:
        st.info(
            "No Miro board URL configured. Set "
            "`DashboardConfig(miro_board_url=...)` (or pass it via the entry "
            "script) to embed the live board here."
        )
        # Visual placeholder so the layout shows where the embed will appear.
        st.markdown(
            """
            <div style="height:600px;border:2px dashed #888;border-radius:8px;
                        display:flex;align-items:center;justify-content:center;
                        color:#666;font-size:1.1em;">
              Miro embed placeholder<br/>
              (configure miro_board_url to render the live board)
            </div>
            """,
            unsafe_allow_html=True,
        )
