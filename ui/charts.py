"""Plotly views; palette and range controls follow the current UI theme."""
import pandas as pd
import plotly.graph_objects as go
from ui.theme import tokens


def style(fig, dark=False, height=285):
    colors = tokens(dark)
    fig.update_layout(template="none", height=height, autosize=True,
                      paper_bgcolor=colors["card"], plot_bgcolor=colors["card"],
                      font=dict(family="Arial, sans-serif", size=11, color=colors["muted"]),
                      margin=dict(l=46, r=18, t=20, b=28),
                      legend=dict(orientation="h", y=1.14, x=0, font=dict(size=10)),
                      hovermode="x unified", hoverlabel=dict(bgcolor=colors["card"], font_color=colors["ink"]),
                      dragmode=False)
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=colors["line"], tickfont=dict(size=10), automargin=True)
    fig.update_yaxes(gridcolor=colors["line"], zeroline=False, tickfont=dict(size=10), automargin=True)
    return fig


def calendar_range(frame, period):
    if frame.empty or period == "All":
        return frame
    months = {"1M": 1, "3M": 3, "6M": 6, "1Y": 12}[period]
    return frame.loc[frame.index >= frame.index[-1] - pd.DateOffset(months=months)]


def index_chart(frame, dark=False, period="6M"):
    colors = tokens(dark)
    frame = calendar_range(frame, period)
    fig = go.Figure()
    close = frame.get("Adj Close", frame["Close"])
    fig.add_trace(go.Scatter(x=frame.index, y=close, name="Nifty 50", mode="lines", line=dict(color=colors["accent"], width=2.6)))
    if "RegimeEMA" in frame:
        fig.add_trace(go.Scatter(x=frame.index, y=frame["RegimeEMA"], name="200 EMA", mode="lines", line=dict(color=colors["purple"], width=1.6, dash="dot")))
    return style(fig, dark, 240)


def price_chart(frame, dark=False, period="6M"):
    colors = tokens(dark)
    frame = calendar_range(frame, period)
    factor = frame.get("Adj Close", frame["Close"]) / frame["Close"]
    fig = go.Figure(go.Candlestick(x=frame.index, open=frame["Open"] * factor, high=frame["High"] * factor,
                                  low=frame["Low"] * factor, close=frame["Close"] * factor, name="Adjusted price",
                                  increasing_line_color=colors["accent"], decreasing_line_color=colors["negative"]))
    for key, name, color in (("EMA_50", "50 EMA", colors["accent"]), ("EMA_200", "200 EMA", colors["purple"])):
        if key in frame:
            fig.add_trace(go.Scatter(x=frame.index, y=frame[key], name=name, mode="lines", line=dict(color=color, width=1.4)))
    style(fig, dark, 315)
    fig.update_layout(xaxis_rangeslider_visible=False)
    return fig


def indicator_chart(frame, kind, dark=False, period="6M"):
    colors = tokens(dark)
    frame = calendar_range(frame, period)
    fig = go.Figure()
    if kind == "Volume":
        fig.add_trace(go.Bar(x=frame.index, y=frame["Volume"], marker_color=colors["purple"], name="Volume"))
        fig.add_trace(go.Scatter(x=frame.index, y=frame["VOL_SMA_20"], line_color=colors["accent"], name="20-session average"))
    elif kind == "RSI":
        fig.add_trace(go.Scatter(x=frame.index, y=frame["RSI_14"], line_color=colors["purple"], name="RSI (14)"))
        fig.add_hrect(y0=60, y1=70, fillcolor=colors["lime"], opacity=.14, line_width=0)
        fig.update_yaxes(range=[0, 100])
    else:
        fig.add_trace(go.Bar(x=frame.index, y=frame["MACDh_12_26_9"], marker_color=colors["purple"], name="Histogram"))
        fig.add_trace(go.Scatter(x=frame.index, y=frame["MACD_12_26_9"], line_color=colors["accent"], name="MACD"))
        fig.add_trace(go.Scatter(x=frame.index, y=frame["MACDs_12_26_9"], line_color=colors["muted"], name="Signal"))
    return style(fig, dark, 190)


def bars(labels, values, dark=False, name="Count", horizontal=False):
    colors = tokens(dark)
    fig = go.Figure(go.Bar(x=values if horizontal else labels, y=labels if horizontal else values,
                          orientation="h" if horizontal else "v", name=name,
                          marker=dict(color=colors["accent"], cornerradius=9)))
    return style(fig, dark, 250)


def equity_chart(history, initial_cash, dark=False):
    colors = tokens(dark)
    fig = go.Figure(go.Scatter(x=[p["date"] for p in history], y=[p["equity"] for p in history],
                              line=dict(color=colors["accent"], width=2.4), mode="lines+markers", name="Account equity", connectgaps=False))
    fig.add_hline(y=initial_cash, line_dash="dot", line_color=colors["muted"])
    return style(fig, dark, 295)


def return_histogram(trades, dark=False):
    colors = tokens(dark)
    fig = go.Figure(go.Histogram(x=[t["realized_pnl_pct"] for t in trades], nbinsx=18,
                                marker_color=colors["purple"], name="Closed trades"))
    style(fig, dark, 270)
    fig.update_layout(xaxis_title="Net return per trade (%)", yaxis_title="Trades")
    return fig
