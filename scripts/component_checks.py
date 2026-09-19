"""Browser checks of the shipped table component and shared visual preview.

These do not replace Streamlit integration tests. --chromium can point to an
already installed browser. Otherwise run `python -m playwright install chromium`.
"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from ui.theme import tokens

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chromium', help='Path to an installed Chromium executable')
    parser.add_argument('--output', type=Path, default=ROOT/'test-results/components')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as p:
        kwargs = {'executable_path': args.chromium} if args.chromium else {}
        browser = p.chromium.launch(headless=True, **kwargs)
        page = browser.new_page(viewport={'width': 1440, 'height': 1080}, device_scale_factor=1)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.set_content((ROOT/'docs/preview.html').read_text(), wait_until='load')
        for label, width, height, dark in [('light',1440,1080,False),('dark',1440,1080,True),('tablet',768,1024,True),('mobile',390,844,False)]:
            page.set_viewport_size({'width':width,'height':height})
            if (page.locator('#theme-toggle').get_attribute('aria-pressed') == 'true') != dark:
                page.locator('#theme-toggle').click()
            page.wait_for_timeout(250)
            assert not page.evaluate('document.documentElement.scrollWidth > innerWidth + 2'), label+' overflows'
            page.screenshot(path=str(args.output/f'preview-{label}.png'), full_page=True)
            results.append({'check': 'shared preview '+label, 'passed':True, 'viewport':f'{width}x{height}'})
        page.set_viewport_size({'width':1440,'height':1080})
        page.locator('#nav-screener').click()
        page.wait_for_timeout(300)
        assert page.locator('#stock .plot-container').count() == 1
        assert page.locator('#screener .nq-rule').count() == 6
        assert page.locator('#screener .nq-rule').last.evaluate('(el)=>el.getBoundingClientRect().bottom <= el.parentElement.getBoundingClientRect().bottom'), 'Six-rule card clips content'
        page.screenshot(path=str(args.output/'preview-screener.png'), full_page=True)
        assert not errors, errors
        results.append({'check':'preview navigation and real Plotly figures','passed':True})
        page.set_content((ROOT/'ui/components/select_table/index.html').read_text(), wait_until='load')
        page.evaluate("window.events=[]; window.addEventListener('message',e=>{if(e.data?.isStreamlitMessage)window.events.push(e.data)})")
        table_args = {'rows':[{'ticker':'A','company':'<img src=x onerror=alert(1)>','score':5,'price':100.5},
                              {'ticker':'B','company':'B Company','score':3,'price':9.2}],
                      'columns':[{'key':'ticker','label':'Company','subkey':'company'},
                                 {'key':'price','label':'Price','format':'money'},
                                 {'key':'score','label':'Score','format':'score'}],
                      'selectable':True,'colors':tokens(False),'max_height':220}
        def render():
            page.evaluate("args=>window.postMessage({type:'streamlit:render',args},'*')", table_args)
            page.wait_for_timeout(80)
        render()
        assert page.locator('tbody img').count() == 0
        assert page.locator('tbody tr').first.inner_text().startswith('A')
        page.get_by_role('button',name='Price',exact=True).click()
        assert page.locator('tbody tr').first.inner_text().startswith('B')
        page.locator('tbody tr').first.focus()
        page.keyboard.press('Enter')
        page.wait_for_timeout(80)
        event = page.evaluate("window.events.filter(e=>e.type==='streamlit:setComponentValue').at(-1)")
        assert event['value']['id'] == 'B'
        assert page.locator('tbody tr[aria-selected="true"]').inner_text().startswith('B')
        table_args.update(colors=tokens(True),selected='A')
        render()
        assert page.evaluate("getComputedStyle(document.getElementById('wrap')).backgroundColor") == 'rgb(25, 41, 35)'
        assert page.locator('tbody tr[aria-selected="true"]').inner_text().startswith('A')
        page.set_viewport_size({'width':320,'height':500})
        page.wait_for_timeout(80)
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth + 2')
        assert page.evaluate("window.events.some(e=>e.type==='streamlit:setFrameHeight' && e.height<=223)")
        table_args['rows'] = []
        render()
        assert 'No rows to display.' in page.locator('tbody').inner_text()
        results.extend({'check':label,'passed':True} for label in [
            'component text escaping', 'component numeric sorting', 'component keyboard selection returns ID',
            'component parent selection synchronization', 'component dark palette',
            'component mobile-contained scroll and resize messages', 'component empty state'])
        browser.close()
    (args.output/'results.json').write_text(json.dumps({'scope':'Shared visual preview and actual table component, not full Streamlit', 'checks':results}, indent=2))
    print(f'{len(results)} shared-preview/component browser checks passed. Results: {args.output}')


if __name__=='__main__':
    main()
