"""Build an offline DESIGN PREVIEW from production HTML/CSS/chart components.

No real market observations are included. This previews the shared visual design,
not a replacement for the Streamlit runtime or evidence of its browser testing.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from html import escape
import json
from plotly.offline import get_plotlyjs
from src.demo import demo_snapshot
from src.instruments import InstrumentRegistry
from src.market import coverage, screen_snapshot, unpack_frame
from src.screener import RULES
from ui.charts import index_chart, price_chart, indicator_chart
from ui.theme import tokens, css
from ui.visuals import brand, page_heading, status_strip, regime_card, coverage_card, metric_card, panel_title, rules_html, money

ROOT = Path(__file__).resolve().parents[1]

def main():
    snapshot = demo_snapshot(InstrumentRegistry.load())
    signals = screen_snapshot(snapshot)
    index = unpack_frame(snapshot['index'])
    selected = next((row for row in signals if row['ticker']=='INFY'), signals[0])
    stock = unpack_frame(snapshot['stocks'][selected['ticker']])
    qualified = sum(row['status']=='Trade-Ready' for row in signals)
    watch = sum(row['status']=='Watchlist' for row in signals)
    component = (ROOT/'ui/components/select_table/index.html').read_text()
    # Keep the design preview fully offline; the live app may load Roboto from Google Fonts.
    component = component.replace('@import url("https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;600;700&display=swap");', '')
    table_args = {'rows': signals[:6], 'columns': [
        {'key':'ticker','label':'Company','subkey':'company'},
        {'key':'close','label':'Close','format':'money','decimals':2,'align':'right'},
        {'key':'score','label':'Conditions','format':'score'},
        {'key':'status','label':'Setup','format':'status'}],
        'colors': tokens(False), 'selectable':False, 'max_height':440}
    fig_data = {}
    for mode in (False, True):
        fig_data['dark' if mode else 'light'] = {
            'market':json.loads(index_chart(index,mode,'6M').to_json()),
            'stock':json.loads(price_chart(stock,mode,'3M').to_json()),
            'volume':json.loads(indicator_chart(stock,'Volume',mode,'3M').to_json())}
    table = f'<iframe id="shortlist" title="Research shortlist" srcdoc="{escape(component, quote=True)}" style="width:100%;border:0;height:440px"></iframe>'
    overview = f'''
    {page_heading('Your daily research workspace', 'Your market. <span>A clearer view.</span>', 'Find the setup. Understand the conditions. Keep risk in perspective.', snapshot['as_of'])}
    {status_strip(snapshot)}
    <div class="preview-hero">
      <div class="preview-stack">{regime_card(snapshot,index)}<button class="preview-action primary" onclick="showPage('screener')">Explore the screener &nbsp; ↗</button></div>
      <section class="nq-card preview-market">{panel_title('The market, in context', 'Nifty 50 and its long-term trend baseline')}<div class="preview-chips"><span>3M</span><span class="active">6M</span><span>1Y</span></div><div id="market"></div></section>
      <div class="preview-stack">{metric_card('Qualified setups',str(qualified),'5–6 conditions met · not a win probability','lime','scan')}{metric_card('On the radar',str(watch),'Watchlist · at least 3 conditions met','','search')}</div>
    </div>
    <div class="preview-bottom"><section class="nq-card">{panel_title('Research shortlist','Explore a qualifying setup in the Screener preview.')}{table}<p class="preview-note">A condition count explains a model output. It is not an investment recommendation.</p></section>{coverage_card(coverage(snapshot))}</div>
    '''
    screener = f'''
    {page_heading('Screener','Find the signal. <span>See the evidence.</span>','One universe. Six transparent conditions. Your research shortlist.',snapshot['as_of'])}
    {status_strip(snapshot)}
    <div class="preview-analysis"><section class="nq-card">{panel_title(selected['ticker']+' · the setup in context','Adjusted analysis prices · synthetic design fixture')}<div class="preview-chips"><span>1M</span><span class="active">3M</span><span>6M</span><span>1Y</span><span>All</span></div><div id="stock"></div><div class="preview-chips"><span class="active">Volume</span><span>RSI</span><span>MACD</span></div><div id="volume"></div></section>
    <div class="preview-stack"><section class="nq-card"><div class="nq-eyebrow">CONDITIONS MET · {selected['score']} / 6</div><div class="nq-symbol">{escape(selected['ticker'])}</div><div class="nq-company">{escape(selected['company'])}</div>{rules_html(selected,RULES)}</section><section class="nq-card nq-lime">{panel_title('Model a paper position','Reference close · not an executable quote')}<div class="nq-card-value">{money(selected['close'],2)}</div><p class="preview-note" style="color:#506638">Synthetic preview cannot create personal paper trades. The full app provides cash allocation, risk sizing and pending orders.</p></section></div></div>
    '''
    extra_css = '''
    *{box-sizing:border-box}body{margin:0;font-family:"Roboto",system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.preview-shell{max-width:1440px;padding:32px 50px;margin:auto}.preview-top{display:flex;align-items:center;justify-content:space-between;gap:20px;background:var(--card);border:1px solid var(--line);border-radius:99px;padding:12px 23px}.preview-top .nq-top-meta{font-size:10px}.theme-button{background:var(--card-soft);border:1px solid var(--line);border-radius:50px;color:var(--ink);padding:11px 15px;white-space:nowrap;cursor:pointer;font:inherit;font-size:11px}.preview-navigation{display:flex;gap:5px;background:var(--card);border:1px solid var(--line);padding:5px;border-radius:99px;margin:17px 0 5px}.preview-navigation button{font:inherit;font-size:12px;flex:1;background:none;border:0;border-radius:99px;padding:12px 20px;color:var(--muted);cursor:pointer}.preview-navigation button.active{background:var(--teal);color:#eaffef}.preview-navigation button:disabled{cursor:default;opacity:.6}.preview-warning{font-size:10px;padding:10px 15px;background:var(--card-soft);border:1px solid var(--line);border-radius:12px;color:var(--warning);line-height:1.5;margin:16px 0 3px}.preview-hero{display:grid;grid-template-columns:1.05fr 1.65fr .92fr;gap:18px;margin-top:18px}.preview-stack{display:flex;flex-direction:column;gap:17px;min-width:0}.preview-stack>.nq-card{flex:1}.preview-market{min-width:0}.preview-action{width:100%;border-radius:99px;border:1px solid var(--line);padding:13px;background:var(--card);color:var(--ink);font:inherit;font-size:12px;cursor:pointer}.preview-action.primary{background:var(--teal);color:#eaffef;border-color:var(--teal)}.preview-bottom{display:grid;grid-template-columns:2.72fr .92fr;gap:18px;margin-top:18px;align-items:start}.preview-bottom>section{min-width:0}.preview-chips{display:flex;gap:4px;margin:8px 0 5px}.preview-chips span{font-size:10px;padding:6px 12px;background:var(--card-soft);color:var(--muted);border-radius:99px}.preview-chips .active{background:var(--teal);color:#eaffef}.preview-note{font-size:10px;color:var(--muted);line-height:1.6;margin:12px 0 0}.preview-analysis{display:grid;grid-template-columns:2.05fr 1fr;gap:18px;margin-top:18px}.preview-analysis>section{min-width:0}.preview-analysis .preview-stack>.nq-card{flex:0 0 auto}#screener{display:none}#stock{min-height:315px}#volume{min-height:165px}
    @media(max-width:1000px){.preview-shell{padding:22px 26px}.preview-top .nq-top-meta{display:none}.preview-hero{grid-template-columns:1fr 1.5fr}.preview-hero>.preview-stack:last-child{grid-column:1/-1;display:grid;grid-template-columns:1fr 1fr}.preview-bottom{grid-template-columns:2fr 1fr}.preview-analysis{grid-template-columns:1.6fr 1fr}.nq-title{font-size:33px}}
    @media(max-width:650px){.preview-shell{padding:14px 16px}.preview-top{border-radius:24px;padding:12px 14px;gap:8px}.preview-navigation{flex-wrap:wrap;border-radius:22px;margin-top:12px}.preview-navigation button{flex:1 1 28%;font-size:10px;padding:10px}.preview-hero,.preview-bottom,.preview-analysis{display:flex;flex-direction:column}.preview-hero>.preview-stack:last-child{display:flex;flex-direction:column}.preview-top .nq-brand-name{font-size:14px}.theme-button{font-size:10px;padding:9px 10px}.preview-market{padding:19px 12px}.nq-card-value{font-size:36px}.preview-warning{font-size:9px}.nq-title{font-size:30px}.nq-regime{min-height:265px}.preview-bottom>.nq-card:last-child{width:100%}}
    '''
    preview_css = css(False).replace('@import url("https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;600;700&display=swap");', '')
    doc = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Nifty Quant Screener — design preview</title><style id="theme">{preview_css}</style><style>{extra_css}</style><script>{get_plotlyjs()}</script></head><body class="nq-preview"><main class="preview-shell"><header class="preview-top">{brand()}<div class="nq-top-meta"><span class="nq-dot"></span>PERSONAL WORKSPACE &nbsp; / &nbsp; NSE · END OF DAY</div><button class="theme-button" id="theme-toggle" aria-pressed="false" onclick="toggleTheme()">☾ &nbsp; Dark mode</button></header><nav class="preview-navigation" aria-label="Preview screens"><button id="nav-overview" class="active" onclick="showPage('overview')">Overview</button><button id="nav-screener" onclick="showPage('screener')">Screener</button><button disabled title="Available in the full Streamlit app">Portfolio</button><button disabled title="Available in the full Streamlit app">Paper trading</button><button disabled title="Available in the full Streamlit app">Backtest</button><button disabled title="Available in the full Streamlit app">Settings</button></nav><div class="preview-warning"><b>SYNTHETIC DESIGN PREVIEW</b> &nbsp; Shared production cards, charts and table component; this is not a screenshot of the full Streamlit runtime. Numbers are generated fixtures, not market observations. Theme and two-screen navigation are interactive.</div><section id="overview">{overview}</section><section id="screener">{screener}</section><footer class="nq-footer"><span>Nifty Quant Screener &nbsp; / &nbsp; Research, not recommendations.</span><span>End-of-day observations · Cash-only simulation · Backup personal changes</span></footer></main><script>
    const palettes={json.dumps({'light':tokens(False),'dark':tokens(True)})}, figures={json.dumps(fig_data)}, tableArgs={json.dumps(table_args)};
    let dark=false;
    function updateTheme(){{const c=palettes[dark?'dark':'light'];Object.entries(c).forEach(([k,v])=>document.documentElement.style.setProperty('--'+(k==='soft'?'card-soft':k),v));document.documentElement.style.setProperty('--positive',c.accent);document.documentElement.style.setProperty('--warning',dark?'#e8bf79':'#98601e');document.documentElement.style.colorScheme=dark?'dark':'light';document.getElementById('theme-toggle').textContent=dark?'☀  Light mode':'☾  Dark mode';document.getElementById('theme-toggle').setAttribute('aria-pressed',String(dark));['market','stock','volume'].forEach(id=>{{const f=figures[dark?'dark':'light'][id];Plotly.react(id,f.data,f.layout,{{displayModeBar:false,scrollZoom:false,responsive:true}});}});renderTable();}}
    function renderTable(){{const frame=document.getElementById('shortlist');frame.contentWindow.postMessage({{type:'streamlit:render',args:{{...tableArgs,colors:palettes[dark?'dark':'light']}}}},'*');}}
    function toggleTheme(){{dark=!dark;updateTheme();}}
    function showPage(name){{['overview','screener'].forEach(id=>{{document.getElementById(id).style.display=id===name?'block':'none';document.getElementById('nav-'+id).classList.toggle('active',id===name);}});window.dispatchEvent(new Event('resize'));}}
    window.addEventListener('message',e=>{{if(e.data?.type==='streamlit:componentReady')renderTable();if(e.data?.type==='streamlit:setFrameHeight')document.getElementById('shortlist').style.height=e.data.height+'px';}});document.getElementById('shortlist').addEventListener('load',renderTable);updateTheme();
    </script></body></html>'''
    path=ROOT/'docs/preview.html'
    path.write_text(doc)
    print(f'Preview: {path} ({len(doc):,} characters)')


if __name__=='__main__':
    main()
