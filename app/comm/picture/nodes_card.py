from collections import Counter
from statistics import median
from typing import List, Optional

from comm.localization.eng_base import BaseLocalization
from lib.date_utils import DAY, today_str
from lib.texts import find_country_emoji
from models.cloud_provider import CloudProviderDB
from models.node_info import NetworkNodes, NodeStatsItem

NODES_TEMPLATE = 'nodes.jinja2'
NODES_CHART_PERIOD = 30 * DAY

MAX_CATEGORIES = 6  # providers and countries that get their own row, the palette of the template has 6 colors
OTHERS_COLOR_INDEX = -1


def nodes_card_filename():
    return f'THORChain-nodes-{today_str()}.png'


def sparse_points(pts: List[NodeStatsItem], interval=DAY) -> List[NodeStatsItem]:
    """About a point per interval counting back from the last one, which is always kept"""
    results = []
    last_ts = None
    for p in reversed(pts):
        if last_ts is None or abs(p.ts - last_ts) >= interval:
            results.append(p)
            last_ts = p.ts
    return list(reversed(results))


def _percent(part, whole):
    return part / whole * 100.0 if whole else 0.0


def _rank(counter: Counter, max_categories, unknown=''):
    """The biggest categories (by count, then by name, the unknown one after its equals) and the rest of them"""
    ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0] == unknown, str(kv[0])))
    if len(ranked) == max_categories + 1:
        max_categories += 1  # a single one is not "others"
    return ranked[:max_categories], ranked[max_categories:]


def build_nodes_card(data: NetworkNodes, chart_pts: Optional[List[NodeStatsItem]], loc: BaseLocalization,
                     usd_per_rune: float = 0.0, provider_db: Optional[CloudProviderDB] = None,
                     max_categories=MAX_CATEGORIES) -> dict:
    """
    Parameters for the nodes.jinja2 template; all texts come localized.
    The providers, the countries and the map are about the active nodes; the map shows the standby ones as dim dots.
    """
    db = provider_db or CloudProviderDB.default()
    active = data.active_nodes
    standby = data.standby_nodes
    n_active = len(active)

    def geo(node):
        return data.ip_info_dict.get(node.ip_address) if node.ip_address else None

    # ---- providers and countries of the active nodes ----
    provider_of = {}
    provider_counter, country_counter = Counter(), Counter()
    country_names = {}
    for node in active:
        info = geo(node)
        provider = db.name_of(info) or loc.TEXT_PIC_UNKNOWN
        provider_of[node.node_address] = provider
        provider_counter[provider] += 1

        code = (info.country_code if info else '') or ''
        country_names[code] = loc.text_country_name(code, info.country_name if info else '') or loc.TEXT_PIC_UNKNOWN
        country_counter[code] += 1

    def others_row(rest):
        count = sum(n for _, n in rest)
        return {'name': f'{loc.TEXT_PIC_OTHERS} ({len(rest)})', 'count': count, 'percent': _percent(count, n_active),
                'ci': OTHERS_COLOR_INDEX, 'flag': '', 'other': True}

    top_providers, rest_providers = _rank(provider_counter, max_categories, unknown=loc.TEXT_PIC_UNKNOWN)
    color_index = {name: i for i, (name, _) in enumerate(top_providers)}
    providers = [
        {'name': name, 'count': n, 'percent': _percent(n, n_active),
         'ci': i if i < MAX_CATEGORIES else OTHERS_COLOR_INDEX}
        for i, (name, n) in enumerate(top_providers)
    ]
    if rest_providers:
        providers.append(others_row(rest_providers))

    top_countries, rest_countries = _rank(country_counter, max_categories)
    countries = [
        {'name': country_names[code], 'code': code, 'flag': find_country_emoji(code) or '',
         'count': n, 'percent': _percent(n, n_active)}
        for code, n in top_countries
    ]
    if rest_countries:
        countries.append(others_row(rest_countries))

    # ---- the map: nodes at the same coordinates make a point ----
    points = {}
    unknown_location = 0

    def point_at(info):
        key = (round(info.latitude, 2), round(info.longitude, 2))
        return points.setdefault(key, {
            'lat': key[0], 'lon': key[1], 'city': info.city or '', 'n': 0, 'standby': 0, 'seg': Counter(),
            # nodes of different countries are never merged into one cluster of a map
            'cc': info.country_code or '',
            'country': loc.text_country_name(info.country_code, info.country_name) or '',
        })

    for node in active:
        info = geo(node)
        if not info or not info.has_location:
            unknown_location += 1
            continue
        point = point_at(info)
        point['n'] += 1
        ci = color_index.get(provider_of[node.node_address], OTHERS_COLOR_INDEX)
        point['seg'][ci if ci < MAX_CATEGORIES else OTHERS_COLOR_INDEX] += 1

    for node in standby:
        info = geo(node)
        if info and info.has_location:
            point_at(info)['standby'] += 1

    for point in points.values():
        # the colors of the palette first, "others" last
        point['seg'] = sorted(point['seg'].items(), key=lambda kv: (kv[0] == OTHERS_COLOR_INDEX, kv[0]))

    # ---- bond ----
    bonds = sorted(n.bond for n in active)
    active_bond = sum(bonds)
    total_bond = data.total_bond
    supply = data.total_rune_supply

    chart = [
        {'ts': int(p.ts), 'bond': p.bond_active_total, 'nodes': int(p.n_active_nodes)}
        for p in sparse_points([p for p in (chart_pts or []) if p.is_valid])
    ]

    return {
        'active_nodes': n_active,
        'standby_nodes': len(standby),
        'total_nodes': len(data.node_info_list),
        'active_bond': active_bond,
        'total_bond': total_bond,
        'active_bond_percent': _percent(active_bond, supply),
        'total_bond_percent': _percent(total_bond, supply),
        'usd_per_rune': usd_per_rune or 0.0,
        'provider_count': len(provider_counter),
        'country_count': len(country_counter),
        'providers': providers,
        'countries': countries,
        'points': sorted(points.values(), key=lambda p: (-p['n'], -p['standby'], p['lat'], p['lon'])),
        'unknown_location': unknown_location,
        'chart': chart,
        'chart_days': NODES_CHART_PERIOD // DAY,
        'bond': {
            'min': bonds[0] if bonds else 0.0,
            'median': median(bonds) if bonds else 0.0,
            'max': bonds[-1] if bonds else 0.0,
            'values': [round(b) for b in bonds],
        },
        't': {
            'title': loc.TEXT_PIC_NODES.upper(),
            'active_nodes': loc.TEXT_PIC_ACTIVE_NODES,
            'active_bond': loc.TEXT_PIC_ACTIVE_BOND,
            'total_nodes': loc.TEXT_PIC_TOTAL_NODES,
            'total_bond': loc.TEXT_PIC_TOTAL_BOND,
            'standby': loc.TEXT_PIC_STANDBY,
            'of_supply': loc.TEXT_PIC_OF_SUPPLY,
            'providers': loc.TEXT_PIC_PROVIDERS,
            'countries': loc.TEXT_PIC_COUNTRIES,
            'of_active_nodes': loc.TEXT_PIC_OF_ACTIVE_NODES,
            'world': loc.TEXT_PIC_WORLD,
            'europe': loc.TEXT_PIC_EUROPE,
            'legend_active': loc.TEXT_PIC_LEGEND_ACTIVE,
            'legend_standby': loc.TEXT_PIC_LEGEND_STANDBY,
            'unknown_location': loc.TEXT_PIC_UNKNOWN_LOCATION,
            'last_days': loc.text_pic_last_days(NODES_CHART_PERIOD // DAY),
            'node_bond': loc.TEXT_PIC_NODE_BOND,
            'min_bond': loc.TEXT_PIC_MIN_BOND,
            'median_bond': loc.TEXT_PIC_MEDIAN_BOND,
            'max_bond': loc.TEXT_PIC_MAX_BOND,
            'note': loc.TEXT_PIC_NODES_NOTE,
        },
    }
