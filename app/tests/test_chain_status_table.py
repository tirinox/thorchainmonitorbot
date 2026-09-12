from lib.date_utils import HOUR, MINUTE
from models.chains import ChainAspect, AspectState, ChainAspectStatus, ChainStatusRow, ChainStatusTable
from notify.public.chain_notify import ChainIncidentTracker

WINDOW = 2 * HOUR


def make_tracker():
    return ChainIncidentTracker(deps=None, window_sec=WINDOW)


def test_aspect_status_paused_wins_over_recent_incident():
    tracker = make_tracker()
    recent = {'BTC:trading': 10 * MINUTE}

    cell = tracker.aspect_status('BTC', ChainAspect.TRADING, True, recent)
    assert cell.state == AspectState.PAUSED
    assert cell.is_paused
    assert not cell.is_unstable


def test_aspect_status_recently_recovered_is_unstable():
    tracker = make_tracker()
    recent = {'BTC:trading': 10 * MINUTE}

    cell = tracker.aspect_status('BTC', ChainAspect.TRADING, False, recent)
    assert cell.state == AspectState.AVAILABLE
    assert cell.is_unstable
    assert cell.incident_ago == 10 * MINUTE

    # a different aspect of the same chain is untouched
    assert not tracker.aspect_status('BTC', ChainAspect.LP, False, recent).is_unstable


def test_aspect_status_no_data():
    cell = make_tracker().aspect_status('BTC', ChainAspect.SIGNING, None, {})
    assert cell.state == AspectState.UNKNOWN
    assert not cell.is_paused
    assert not cell.is_unstable


def make_row(chain, paused_aspect=None, recent_aspect=None):
    aspects = {a: ChainAspectStatus(AspectState.AVAILABLE) for a in ChainAspect.ALL}
    if paused_aspect:
        aspects[paused_aspect] = ChainAspectStatus(AspectState.PAUSED)
    if recent_aspect:
        aspects[recent_aspect] = ChainAspectStatus(AspectState.AVAILABLE, 30 * MINUTE)
    return ChainStatusRow(chain=chain, aspects=aspects)


def test_overall_status():
    healthy = make_row('BTC')
    recovered = make_row('LTC', recent_aspect=ChainAspect.TRADING)
    halted = make_row('GAIA', paused_aspect=ChainAspect.TRADING)

    assert ChainStatusTable([healthy]).overall_status == ChainStatusTable.OPERATIONAL
    assert ChainStatusTable([healthy, recovered]).overall_status == ChainStatusTable.UNSTABLE
    assert ChainStatusTable([healthy, recovered, halted]).overall_status == ChainStatusTable.DEGRADED


def test_table_to_dict():
    table = ChainStatusTable(
        rows=[make_row('BTC'), make_row('LTC', recent_aspect=ChainAspect.LP),
              make_row('GAIA', paused_aspect=ChainAspect.TRADING)],
        recent_window_sec=WINDOW
    )
    d = table.to_dict()

    assert d['total_chains'] == 3
    assert d['paused_chains'] == ['GAIA']
    assert d['unstable_chains'] == ['LTC']
    assert d['overall_status'] == ChainStatusTable.DEGRADED
    assert d['recent_window_sec'] == WINDOW
    assert [c['key'] for c in d['columns']] == list(ChainAspect.ALL)

    # the template reads every cell by column key, so all of them must be present
    for chain in d['chains']:
        assert set(chain['aspects'].keys()) == set(ChainAspect.ALL)

    assert d['chains'][1]['aspects']['lp']['unstable'] is True
    assert d['chains'][2]['aspects']['trading']['state'] == AspectState.PAUSED


def test_chain_logo():
    assert make_row('BTC').logo == 'BTC.BTC'
    assert make_row('GAIA').logo == 'GAIA.ATOM'
    # Base's gas asset is ETH, but the picture must show the Base logo
    assert make_row('BASE').logo == 'BASE'
