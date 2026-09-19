"""Session-scoped visual tokens; never mutate global Streamlit configuration."""
from pathlib import Path

LIGHT = {"bg": "#eff2ee", "card": "#ffffff", "soft": "#f5f7f3", "ink": "#172d27", "muted": "#6d7d74", "line": "#e0e7df", "teal": "#105d50", "accent": "#167b68", "lime": "#d9f98b", "purple": "#a998e4", "negative": "#b65048"}
DARK = {"bg": "#101b18", "card": "#192923", "soft": "#20342c", "ink": "#ecf4e9", "muted": "#a6b9ac", "line": "#32483c", "teal": "#145e4e", "accent": "#82c8a2", "lime": "#d9f98b", "purple": "#b8a5ee", "negative": "#f19c8b"}


def tokens(dark=False):
    return DARK if dark else LIGHT


def css(dark=False):
    colors = tokens(dark)
    base = (Path(__file__).resolve().parents[1] / "assets/theme.css").read_text()
    override = ":root{" + ";".join(f"--{key}:{value}" for key, value in colors.items() if key != "soft") + f";--card-soft:{colors['soft']};--positive:{colors['accent']};--warning:{'#e8bf79' if dark else '#98601e'};color-scheme:{'dark' if dark else 'light'}" + "}"
    return base + "\n" + override


def apply_theme(dark=False):
    import streamlit as st
    st.markdown("<style>" + css(dark) + "</style>", unsafe_allow_html=True)
