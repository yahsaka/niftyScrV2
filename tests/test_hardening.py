from copy import deepcopy
import json
import pytest
from src.config import StrategyConfig, ExecutionConfig
from src.execution import process_ledger, validate_ledger
from src.market import pack_frame
from src.portfolio import analyze_holdings
from src.storage import new_workspace, validate_workspace, import_backup

@pytest.mark.parametrize('content',[b'[]',b'null',b'1',b'"text"'])
def test_backup_root_must_be_object(content):
    with pytest.raises(ValueError):
        import_backup(content)

@pytest.mark.parametrize('mutate',[
    lambda w: w['preferences'].update(dark_mode='yes'),
    lambda w: w.update(archived_accounts={}),
    lambda w: w['saved_filters'].update(bad={'score':7}),
    lambda w: w['saved_filters'].update(bad={'triggers':['NOT_A_RULE']}),
    lambda w: w['saved_filters'].update(bad={'preset':'unexpected'})])
def test_workspace_validates_restored_controls(mutate):
    workspace=new_workspace();mutate(workspace)
    with pytest.raises(ValueError):
        validate_workspace(workspace)

@pytest.mark.parametrize('config',[lambda:StrategyConfig(True,5),lambda:ExecutionConfig(hold_sessions=True)])
def test_boolean_not_integer_configuration(config):
    with pytest.raises(ValueError):config()

# Specific regression around stop-first execution and missing data AFTER closure.
def test_missing_future_data_does_not_block_already_closed_trade(ledger,bars):
    frame=bars.copy()
    frame.loc[frame.index[1],'Low']=90
    cut=frame.drop(frame.index[3])
    result=process_ledger(ledger,{'INFY':cut},str(frame.index[5].date()),list(frame.index[:6].strftime('%Y-%m-%d')))
    assert result['trades'][0]['status']=='CLOSED'
    assert result['trades'][0]['sessions_held']==1


def test_invalid_nonpositive_portfolio_price_remains_unpriced(bars):
    frame=bars.copy();frame.loc[frame.index[-1],'Close']=0
    day=frame.index[-1].date().isoformat()
    snapshot={'as_of':day,'stocks':{'INFY':{**pack_frame(frame),'quality':'Current','data_as_of':day}}}
    report=analyze_holdings([{'ticker':'INFY','quantity':1,'average_price':100}],snapshot)
    assert report['rows'][0]['price'] is None
    assert report['rows'][0]['pnl'] is None
    assert report['unpriced']==1


def test_closed_pnl_must_reconcile(ledger,bars):
    result=process_ledger(ledger,{'INFY':bars},bars.index[5].date().isoformat())
    result['trades'][0]['realized_pnl']+=100
    with pytest.raises(ValueError,match='reconcile'):
        validate_ledger(result)
