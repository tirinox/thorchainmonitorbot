import json
import os
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from comm.localization.eng_base import EnglishLocalization
from comm.localization.rus import RussianLocalization
from comm.picture.nodes_card import build_nodes_card, sparse_points, NODES_TEMPLATE, OTHERS_COLOR_INDEX
from lib.config import Config
from lib.date_utils import DAY, HOUR
from models.cloud_provider import CloudProviderDB, CloudProvider, clean_company_name
from models.geo_ip import LocationInfo, parse_as
from models.node_info import NodeInfo, NetworkNodes, NodeStatsItem
from tests.fakes import FakeDB

CFG = Config(name='./tests/test_config.yaml')


def geo(ip, as_text, org='', isp='', lat=52.2, lon=21.0, country='Poland', code='PL', city='Warsaw'):
    """As ip-api.com answers"""
    return LocationInfo.from_alt_json({
        'query': ip, 'as': as_text, 'org': org, 'isp': isp,
        'lat': lat, 'lon': lon, 'country': country, 'countryCode': code, 'city': city,
    })


# ---------------- GeoIP ----------------

def test_parse_as():
    assert parse_as('AS14061 DigitalOcean, LLC') == (14061, 'DigitalOcean, LLC')
    assert parse_as('AS174') == (174, '')
    assert parse_as('') == (0, '')
    assert parse_as(None) == (0, '')
    assert parse_as('DigitalOcean') == (0, '')


def test_location_info_from_ip_api():
    info = geo('1.1.1.1', 'AS20473 The Constant Company, LLC', org='', isp='Choopa', city='Sydney')
    assert (info.asn, info.as_name, info.isp) == (20473, 'The Constant Company, LLC', 'Choopa')
    assert info.org == 'Choopa'  # an empty org falls back to the ISP
    assert info.has_location
    assert not LocationInfo.from_alt_json({'query': '10.0.0.1', 'status': 'fail'}).has_location


def test_node_from_db_restores_location():
    node = NodeInfo('Active', 'thor1', 100.0, '1.2.3.4')
    node.ip_info = geo('1.2.3.4', 'AS14061 DigitalOcean, LLC')
    raw = json.loads(json.dumps(asdict(node)))
    assert isinstance(raw['ip_info'], list)

    restored = NodeInfo.from_db(raw)
    assert restored.ip_info == node.ip_info
    assert restored.flag_emoji == '🇵🇱'

    # a location saved before the AS fields were added
    raw['ip_info'] = raw['ip_info'][:7]
    old = NodeInfo.from_db(raw)
    assert old.ip_info.city == 'Warsaw' and old.ip_info.asn == 0

    raw['ip_info'] = None
    assert NodeInfo.from_db(raw).flag_emoji == ''


# ---------------- providers ----------------

@pytest.mark.parametrize('name, expected', [
    ('DigitalOcean, LLC', 'DigitalOcean'),
    ('MEVSPACE sp. z o.o.', 'Mevspace'),  # all capitals are too loud; the real one is in the database
    ('Leaseweb UK Limited', 'Leaseweb UK'),
    ('LUMADOCK LTD', 'Lumadock'),
    ('Hetzner Online GmbH', 'Hetzner Online'),
    ('OVH SAS', 'OVH'),
    ('Level 3 Parent, LLC', 'Level 3'),
    ('FlokiNET ehf', 'FlokiNET'),
    ('LLC', 'LLC'),  # nothing but the legal form: left as it is
    ('', ''),
    (None, ''),
])
def test_clean_company_name(name, expected):
    assert clean_company_name(name) == expected


def test_provider_database_file():
    db = CloudProviderDB.from_file()
    assert len(db.providers) > 80

    names = [p.name for p in db.providers]
    assert len(names) == len(set(names))

    asn_owner = {}
    for p in db.providers:
        assert p.asn or p.match, p.name
        for asn in p.asn:
            assert asn not in asn_owner, f'AS{asn} is of both {asn_owner[asn]} and {p.name}'
            asn_owner[asn] = p.name


@pytest.mark.parametrize('as_text, org, isp, expected', [
    # the same cloud whatever GeoIP calls the org
    ('AS14061 DigitalOcean, LLC', 'Digital Ocean', 'DigitalOcean, LLC', 'DigitalOcean'),
    ('AS14061 DigitalOcean, LLC', 'Digitalocean', 'DIGITALOCEAN', 'DigitalOcean'),
    ('AS20473 The Constant Company, LLC', 'Vultr Holdings, LLC', 'Choopa', 'Vultr'),
    ('AS20473 The Constant Company, LLC', '', 'SGP VULTR', 'Vultr'),
    ('AS205544 Leaseweb UK Limited', 'Leaseweb UK Limited', '', 'Leaseweb'),
    ('AS28753 Leaseweb Deutschland GmbH', 'SERV LT Joint Stock Company (UAB)', 'Leaseweb DE', 'Leaseweb'),
    ('AS203919 LUMADOCK LTD', 'LifeinCloud LTD', 'Lumadock LTD', 'LifeinCloud'),
    ('AS201814 MEVSPACE sp. z o.o.', 'SKYTECHNOLOGY', 'Cogent Communications', 'MEVSPACE'),
    ('AS16509 Amazon.com, Inc.', 'AWS EC2 (us-east-2)', 'Amazon.com, Inc.', 'AWS'),
    ('AS396982 Google LLC', 'Google Cloud (us-east4)', 'Google LLC', 'Google Cloud'),
    # an AS that is not listed, found by a word of its name
    ('AS99999 Hetzner Online GmbH', '', '', 'Hetzner'),
    ('', 'OVH US LLC', '', 'OVHcloud'),
    # unknown ones get the tidied AS name, then the org
    ('AS64500 Some Hosting Ltd', 'whatever', '', 'Some Hosting'),
    ('', 'Novohost LLC', '', 'Novohost'),  # "ovh" is not a whole word here
    ('', '', '', ''),
])
def test_provider_name(as_text, org, isp, expected):
    db = CloudProviderDB.default()
    assert db.name_of(geo('1.1.1.1', as_text, org, isp)) == expected


def test_provider_of_nothing():
    db = CloudProviderDB([CloudProvider('Foo', asn=(1,), match=('foo cloud',))])
    assert db.name_of(None) == ''
    assert db.find(None) is None
    assert db.name_of(geo('1.1.1.1', 'AS1 Bar')) == 'Foo'
    assert db.name_of(geo('1.1.1.1', 'AS2 The Foo Cloud Inc.')) == 'Foo'
    assert db.name_of(geo('1.1.1.1', 'AS2 Foo Clouds Inc.')) == 'Foo Clouds'


# ---------------- the card ----------------

def _node(n, status=NodeInfo.ACTIVE, bond=1_000_000.0, ip=True):
    return NodeInfo(status, f'thor{n}', bond, f'10.0.0.{n}' if ip else '')


def _network():
    do, mev, vultr = 'AS14061 DigitalOcean, LLC', 'AS201814 MEVSPACE sp. z o.o.', 'AS20473 The Constant Company, LLC'
    warsaw = dict(lat=52.18, lon=21.06, country='Poland', code='PL', city='Warsaw')
    sydney = dict(lat=-33.9, lon=151.19, country='Australia', code='AU', city='Sydney')
    nodes = [
        _node(1, bond=300_000), _node(2, bond=500_000), _node(3, bond=900_000),  # Warsaw: MEVSPACE x2, DO
        _node(4), _node(5, bond=1_300_000),  # Sydney: Vultr under two org names
        _node(6),  # no geo info for its address
        _node(7, ip=False),  # no address at all
        _node(8, NodeInfo.STANDBY, bond=400_000), _node(9, NodeInfo.STANDBY, bond=0),
        _node(10, NodeInfo.DISABLED, bond=0),
    ]
    ip_info = {
        '10.0.0.1': geo('10.0.0.1', mev, **warsaw),
        '10.0.0.2': geo('10.0.0.2', mev, org='SKYTECHNOLOGY', **warsaw),
        '10.0.0.3': geo('10.0.0.3', do, **warsaw),
        '10.0.0.4': geo('10.0.0.4', vultr, org='Vultr Holdings, LLC', **sydney),
        '10.0.0.5': geo('10.0.0.5', vultr, isp='Choopa', **sydney),
        '10.0.0.6': None,
        '10.0.0.8': geo('10.0.0.8', do, **warsaw),
        '10.0.0.9': geo('10.0.0.9', do, lat=1.32, lon=103.69, country='Singapore', code='SG', city='Singapore'),
    }
    return NetworkNodes(nodes, ip_info, total_rune_supply=100_000_000)


def test_card_providers_and_countries():
    card = build_nodes_card(_network(), [], EnglishLocalization(CFG), usd_per_rune=2.0)

    assert (card['active_nodes'], card['standby_nodes'], card['total_nodes']) == (7, 2, 10)

    providers = {p['name']: p for p in card['providers']}
    assert {name: p['count'] for name, p in providers.items()} == {
        'MEVSPACE': 2, 'Vultr': 2, 'Unknown': 2, 'DigitalOcean': 1,
    }
    assert card['provider_count'] == 4
    assert sum(p['count'] for p in card['providers']) == 7
    assert abs(sum(p['percent'] for p in card['providers']) - 100) < 1e-6
    # the biggest first, the same count by name and the unknown after them; the colors go in this order
    assert [(p['name'], p['ci']) for p in card['providers']] == [
        ('MEVSPACE', 0), ('Vultr', 1), ('Unknown', 2), ('DigitalOcean', 3),
    ]

    countries = [(c['name'], c['flag'], c['count']) for c in card['countries']]
    assert countries == [('Poland', '🇵🇱', 3), ('Australia', '🇦🇺', 2), ('Unknown', '', 2)]
    assert card['country_count'] == 3


def test_card_map_points():
    card = build_nodes_card(_network(), [], EnglishLocalization(CFG))
    colors = {p['name']: p['ci'] for p in card['providers']}

    points = {p['city']: p for p in card['points']}
    assert set(points) == {'Warsaw', 'Sydney', 'Singapore'}

    warsaw = points['Warsaw']
    assert (warsaw['lat'], warsaw['lon'], warsaw['n'], warsaw['standby']) == (52.18, 21.06, 3, 1)
    assert (warsaw['cc'], warsaw['country']) == ('PL', 'Poland')
    assert dict(warsaw['seg']) == {colors['MEVSPACE']: 2, colors['DigitalOcean']: 1}

    assert dict(points['Sydney']['seg']) == {colors['Vultr']: 2}
    assert (points['Singapore']['n'], points['Singapore']['standby'], points['Singapore']['seg']) == (0, 1, [])

    # the two active nodes without geo data are counted, not put on the map
    assert card['unknown_location'] == 2
    assert sum(p['n'] for p in card['points']) + card['unknown_location'] == card['active_nodes']
    # the biggest point first
    assert card['points'][0]['city'] == 'Warsaw'


def test_card_bond():
    card = build_nodes_card(_network(), [], EnglishLocalization(CFG), usd_per_rune=2.0)
    assert card['active_bond'] == 6_000_000
    assert card['total_bond'] == 6_400_000
    assert card['active_bond_percent'] == 6.0
    assert card['total_bond_percent'] == pytest.approx(6.4)
    assert card['usd_per_rune'] == 2.0
    assert card['bond'] == {
        'min': 300_000, 'median': 1_000_000, 'max': 1_300_000,
        'values': [300_000, 500_000, 900_000, 1_000_000, 1_000_000, 1_000_000, 1_300_000],
    }


def test_card_others():
    # 9 providers, a node each: 6 get a row and a color, 3 are "others"
    nodes = [_node(i) for i in range(1, 10)]
    ip_info = {n.ip_address: geo(n.ip_address, f'AS{64500 + i} Host{i:02d} Ltd') for i, n in enumerate(nodes)}
    ip_info[nodes[8].ip_address] = geo(nodes[8].ip_address, 'AS64508 Host08 Ltd', lat=10, lon=10, city='Far')
    card = build_nodes_card(NetworkNodes(nodes, ip_info), [], EnglishLocalization(CFG))

    assert [p['ci'] for p in card['providers']] == [0, 1, 2, 3, 4, 5, OTHERS_COLOR_INDEX]
    others = card['providers'][-1]
    assert (others['name'], others['count'], others['other']) == ('Others (3)', 3, True)
    assert card['provider_count'] == 9

    # on the map "others" go last in a point
    by_city = {p['city']: p for p in card['points']}
    assert by_city['Warsaw']['seg'] == [(0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (5, 1), (OTHERS_COLOR_INDEX, 2)]
    assert by_city['Far']['seg'] == [(OTHERS_COLOR_INDEX, 1)]

    # a single one beyond the limit is shown by its name, in the color of "others"
    card = build_nodes_card(NetworkNodes(nodes[:7], ip_info), [], EnglishLocalization(CFG))
    assert [p['name'] for p in card['providers']][-1] == 'Host06'
    assert [p['ci'] for p in card['providers']] == [0, 1, 2, 3, 4, 5, OTHERS_COLOR_INDEX]
    assert not any(p.get('other') for p in card['providers'])


def test_card_is_localized():
    card = build_nodes_card(_network(), [], RussianLocalization(CFG))
    assert card['t']['title'] == 'НОДЫ'
    assert 'прокси' in card['t']['note']
    assert [c['name'] for c in card['countries']] == ['Польша', 'Австралия', 'Неизвестно']

    card = build_nodes_card(_network(), [], EnglishLocalization(CFG))
    assert card['t']['title'] == 'NODES'
    assert 'proxy' in card['t']['note']
    assert all(card['t'].values())


def test_card_of_no_nodes():
    card = build_nodes_card(NetworkNodes(), None, EnglishLocalization(CFG))
    assert card['active_nodes'] == 0
    assert card['providers'] == card['countries'] == card['points'] == card['chart'] == []
    assert card['bond'] == {'min': 0.0, 'median': 0.0, 'max': 0.0, 'values': []}


def _stat(ts, nodes=100, bond=90e6):
    return NodeStatsItem(ts, 3e5, 9e5, 1.2e6, bond, bond * 1.1, 200, nodes)


def test_chart_points():
    end = 1_791_000_000
    hourly = [_stat(end - h * HOUR, nodes=100 + (h < 30)) for h in range(5 * 24, -1, -1)]

    sparse = sparse_points(hourly)
    assert [p.ts for p in sparse] == [end - d * DAY for d in range(5, -1, -1)]
    assert sparse_points([]) == []

    broken = _stat(end + HOUR, nodes=0, bond=0)  # recorded while the node list was empty
    card = build_nodes_card(_network(), hourly + [broken], EnglishLocalization(CFG))
    assert [p['ts'] for p in card['chart']] == [end - d * DAY for d in range(5, -1, -1)]
    assert card['chart'][-1] == {'ts': end, 'bond': 90e6, 'nodes': 101}
    assert card['chart'][0]['nodes'] == 100


# ---------------- the template ----------------

@pytest.fixture(scope='module')
def renderer():
    pytest.importorskip('playwright')
    from renderer.engine import RendererEngine
    return RendererEngine(templates_dir=os.path.join(os.path.dirname(__file__), '..', 'renderer', 'templates'))


def _chart():
    return [_stat(1_791_000_000 - d * DAY, nodes=100 - d) for d in range(10, -1, -1)]


@pytest.mark.parametrize('params', [
    build_nodes_card(_network(), _chart(), EnglishLocalization(CFG), usd_per_rune=2.0),
    build_nodes_card(_network(), [], RussianLocalization(CFG)),
    build_nodes_card(NetworkNodes(), None, EnglishLocalization(CFG)),
], ids=['full', 'ru-no-chart-no-price', 'empty'])
def test_template_renders(renderer, params):
    # the parameters travel to the renderer as JSON
    params = json.loads(json.dumps(params))
    result = renderer.render_template_to_html(NODES_TEMPLATE, params)
    assert (result.viewport_width, result.viewport_height) == (1600, 1350)
    html = result.html_content
    assert params['t']['title'] in html
    assert params['t']['note'] in html
    assert ('bondChart' in html) == (len(params['chart']) >= 2)
    for p in params['providers']:
        assert p['name'] in html
    if params['usd_per_rune']:
        assert '$12.0M' in html  # the active bond in dollars
    else:
        assert '$' not in html.split('<div class="layout">')[1].split('<script>')[0]


def test_template_renders_the_demos(renderer):
    from renderer.demo import load_demo
    for name in ('nodes', 'nodes_ru'):
        demo = load_demo(name)
        assert demo['template_name'] == NODES_TEMPLATE
        html = renderer.render_template_to_html(demo['template_name'], demo['parameters']).html_content
        assert 'DigitalOcean' in html
        assert demo['parameters']['t']['note'] in html


# ---------------- the churn notifier ----------------

@pytest.mark.asyncio
async def test_last_churn_start_never_saved():
    from notify.public.node_churn_notify import NodeChurnNotifier
    notifier = NodeChurnNotifier(SimpleNamespace(cfg=CFG, db=FakeDB()))
    assert await notifier.get_last_churn_start_ts() is None

    await notifier._set_last_churn_start_ts()
    assert await notifier.get_last_churn_start_ts() > 0


@pytest.mark.asyncio
async def test_finish_churn_without_saved_nodes():
    from notify.public.node_churn_notify import NodeChurnNotifier
    notifier = NodeChurnNotifier(SimpleNamespace(cfg=CFG, db=FakeDB()))
    sent = []
    notifier.pass_data_to_listeners = lambda *a, **kw: sent.append(a)

    await notifier._set_churning_stage(NodeChurnNotifier.MIGRATION)
    await notifier._finish_churn()

    # nothing to tell, and it is not tried again on the next tick
    assert not sent
    assert await notifier.get_churning_stage() == ''
