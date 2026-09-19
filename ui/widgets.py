from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from ui.theme import tokens

_select_table = components.declare_component("nifty_select_table", path=str(Path(__file__).parent / "components/select_table"))


def table(rows, columns, key, dark=False, selected=None, selectable=False, max_height=490):
    return _select_table(rows=rows, columns=columns, colors=tokens(dark), selected=selected,
                         selectable=selectable, max_height=max_height, key=key, default=None)


def html(content):
    st.markdown(content, unsafe_allow_html=True)


def plot(fig, key=None):
    st.plotly_chart(fig, width="stretch", theme=None, key=key,
                    config={"displayModeBar": False, "scrollZoom": False, "responsive": True})


def go_to(screen, ticker=None):
    st.session_state["_pending_route"] = screen
    if ticker:
        st.session_state["selected_ticker"] = ticker


def notice(text, level="info"):
    getattr(st, level)(text)
