"""Escaped, reusable HTML visuals; all actionable controls are native/component UI."""
from html import escape
import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from src.freshness import freshness

ICONS = {
    "arrow": '<path d="M7 17 17 7M7 7h10v10"/>',
    "grid": '<rect x="4" y="4" width="6" height="6" rx="1.5"/><rect x="14" y="4" width="6" height="6" rx="1.5"/><rect x="4" y="14" width="6" height="6" rx="1.5"/><rect x="14" y="14" width="6" height="6" rx="1.5"/>',
    "chart": '<path d="M4 19V5M4 19h16M8 15l4-5 4 2 4-7"/>',
    "scan": '<path d="M8 3H4v4m12-4h4v4M4 17v4h4m8 0h4v-4M5 12h14"/>',
    "shield": '<path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6zM8 12l3 3 5-6"/>',
    "folder": '<path d="M3 7V5h7l2 3h9v11H3z"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v6l4 2"/>',
    "search": '<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',
    "wallet": '<path d="M4 6h15v14H4V6l12-3v3M15 11h6v5h-6z"/>',
}


def icon(name="arrow"):
    return f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS.get(name, ICONS["arrow"])}</svg>'


def _indian_number(value, decimals=0):
    sign = "-" if value < 0 else ""
    absolute = abs(float(value))
    fixed = f"{absolute:.{decimals}f}"
    whole, dot, fraction = fixed.partition(".")
    if len(whole) > 3:
        tail = whole[-3:]
        head = whole[:-3]
        groups = []
        while head:
            groups.append(head[-2:])
            head = head[:-2]
        whole = ",".join(reversed(groups)) + "," + tail
    suffix = dot + fraction if decimals else ""
    return sign + whole + suffix


def money(value, decimals=0):
    if value is None or not isinstance(value, (float, int)) or not math.isfinite(value):
        return "—"
    return "₹" + _indian_number(value, decimals)


def pct(value, signed=False, decimals=1):
    if value is None or not math.isfinite(float(value)):
        return "—"
    return f"{value:+.{decimals}f}%" if signed else f"{value:.{decimals}f}%"


def pretty_date(value):
    try:
        return datetime.fromisoformat(str(value)).strftime("%d %b %Y")
    except (ValueError, TypeError):
        return "Not yet available"


def brand():
    return '''<div class="nq-brand"><svg viewBox="0 0 40 40" aria-hidden="true"><rect width="40" height="40" rx="13" fill="#105d50"/><path d="M12 28V13h5l7 11V13h4v15h-5l-7-11v11z" fill="#d9f98b"/></svg><span class="nq-brand-name">Nifty Quant Screener</span></div>'''


def page_heading(eyebrow, title, subtitle, as_of=None):
    return f'<div class="nq-page-head"><div><div class="nq-eyebrow">{escape(eyebrow)}</div><div class="nq-title">{title}</div><p class="nq-subtitle">{escape(subtitle)}</p></div><div class="nq-date">{escape(pretty_date(as_of))} &nbsp; · &nbsp; EOD</div></div>'


def status_strip(snapshot):
    state = freshness(snapshot.get("as_of"))
    status = "Synthetic preview" if snapshot.get("is_demo") else state["status"]
    refresh = snapshot.get("generated_at")
    try:
        parsed = datetime.fromisoformat(str(refresh).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        refresh = parsed.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%d %b · %H:%M IST")
    except (TypeError, ValueError):
        refresh = "Not run"
    return f'''<div class="nq-status-strip"><span class="{'nq-warning' if not state['is_fresh'] else ''}">● &nbsp; {escape(status)}</span><span>Prices as of &nbsp;<b>{escape(pretty_date(snapshot.get('as_of')))}</b></span><span>Refreshed &nbsp;<b>{escape(refresh)}</b></span><span>Source &nbsp;<b>{'Synthetic fixtures' if snapshot.get('is_demo') else 'Yahoo Finance'}</b></span></div>'''


def metric_card(title, value, foot="", tone="", symbol=None):
    tone_class = f" nq-{tone}" if tone else ""
    marker = f'<span class="nq-card-icon">{icon(symbol)}</span>' if symbol else ""
    return f'<div class="nq-card{tone_class}"><div class="nq-card-title"><span>{escape(str(title))}</span>{marker}</div><div class="nq-card-value">{escape(str(value))}</div><div class="nq-card-foot">{escape(foot)}</div></div>'


def empty(title, body, symbol="scan"):
    return f'<div class="nq-empty"><div class="nq-empty-mark">{icon(symbol)}</div><strong>{escape(title)}</strong><p>{escape(body)}</p></div>'


def panel_title(title, subtitle=""):
    return f'<div class="nq-panel-title">{escape(title)}</div><div class="nq-panel-sub">{escape(subtitle)}</div>'


def regime_card(snapshot, index_frame):
    regime = snapshot.get("market_regime", "Unknown")
    price = float(index_frame["Close"].iloc[-1]) if not index_frame.empty else None
    note = {"Bullish": "The 200 EMA / three-session filter permits setup evaluation.",
            "Bearish": "Long setup classification is paused by the market filter.",
            "Unknown": "A valid benchmark snapshot is needed before evaluating setups."}.get(regime, "")
    return f'''<div class="nq-card nq-teal nq-regime"><div><div class="nq-card-title"><span>NIFTY 50 · MARKET REGIME</span><span class="nq-arrow">{icon('chart')}</span></div><div class="nq-card-value">{escape(regime)}</div><div class="nq-card-foot">{escape(note)}</div></div><div><div class="nq-eyebrow">BENCHMARK CLOSE</div><div style="font-size:26px;letter-spacing:-.8px">{f'{price:,.2f}' if price else '—'}</div><div class="nq-card-foot">Model classification, not a market forecast.</div></div></div>'''


def coverage_card(counts):
    ratio = counts["percent"]
    circumference = 2 * math.pi * 73
    dash = circumference * ratio / 100
    return f'''<div class="nq-card">{panel_title('A clearer picture', 'Coverage of the configured stock universe')}<div class="nq-coverage-wrap"><svg viewBox="0 0 176 176" role="img" aria-label="{ratio:.1f} percent analyzed"><circle cx="88" cy="88" r="73" fill="none" stroke="var(--line)" stroke-width="14"/><circle cx="88" cy="88" r="73" fill="none" stroke="var(--positive)" stroke-width="14" stroke-linecap="round" stroke-dasharray="{dash:.3f} {circumference:.3f}" transform="rotate(-90 88 88)"/></svg><div class="nq-coverage-number">{ratio:.0f}%<small>analyzed</small></div></div><div class="nq-legend-row"><span><i class="nq-swatch"></i>Current &amp; analyzed</span><b>{counts['analyzed']}</b></div><div class="nq-legend-row"><span><i class="nq-swatch" style="background:var(--line)"></i>Missing / not assessed</span><b>{counts['unassessed']}</b></div></div>'''


def rules_html(setup, rules):
    return "".join(f'<div class="nq-rule {"nq-rule-pass" if setup["checks"].get(code) else ""}"><div class="nq-rule-check">{"✓" if setup["checks"].get(code) else "–"}</div><div><div class="nq-rule-name">{escape(title)}</div><div class="nq-rule-note">{escape(note)}</div></div></div>' for code, (title, note) in rules.items())
