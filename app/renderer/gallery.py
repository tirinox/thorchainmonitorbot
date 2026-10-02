import json
import os

from .demo import available_demo_templates, load_demo
from .engine import RendererEngine

GALLERY_PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gallery.html')

# template => section title; the sections go in this order, the rest follow alphabetically
TEMPLATE_GROUPS = {
    'achievement.jinja2': 'Achievements',
    'swap_start.jinja2': 'Swap started',
    'swap_finished.jinja2': 'Swap finished',
    'weekly_stats.jinja2': 'Weekly stats',
    'price.jinja2': 'Price',
    'rune_burn_and_income.jinja2': 'RUNE burn & income',
    'rune_transfer_stats.jinja2': 'RUNE transfers',
    'pol_summary_adr024.jinja2': 'POL summary',
    'secured_asset_summary.jinja2': 'Secured assets',
    'trade_asset_summary.jinja2': 'Trade assets',
    'tcy_info.jinja2': 'TCY',
    'rujira.jinja2': 'Rujira',
    'app_layer_stats.jinja2': 'App layer',
    'limit_swap_stats.jinja2': 'Limit swaps',
    'rapid_swap_stats.jinja2': 'Rapid swaps',
    'mimir_voting.jinja2': 'Mimir voting',
    'chain_halt.jinja2': 'Chain halt',
}
DEBUG_GROUP = 'Debug'
DEBUG_TEMPLATES = {'foo.jinja2', 'example.jinja2'}


def _group_of(name: str, template: str) -> str:
    if name.startswith('dbg_') or template.startswith('dbg_') or template in DEBUG_TEMPLATES:
        return DEBUG_GROUP
    return TEMPLATE_GROUPS.get(template) or template.removesuffix('.jinja2').replace('_', ' ').capitalize()


def _group_sort_key(group: str):
    order = list(TEMPLATE_GROUPS.values())
    if group in order:
        return 0, order.index(group), ''
    return (2 if group == DEBUG_GROUP else 1), 0, group


def demo_catalog(renderer: RendererEngine) -> list:
    """Every demo with its section, texts and viewport size; a demo that fails to render keeps its error"""
    items = []
    for name in available_demo_templates():
        item = {'name': name, 'template': '', 'group': DEBUG_GROUP, 'title': name, 'subtitle': '',
                'lang': 'ru' if name.endswith('_ru') else 'en', 'order': 0, 'w': 1280, 'h': 720, 'error': ''}
        try:
            demo = load_demo(name)
            template = demo['template_name']
            meta = demo.get('meta') or {}
            item.update(
                template=template,
                group=_group_of(name, template),
                title=meta.get('title') or name,
                subtitle=meta.get('subtitle', ''),
                lang=meta.get('lang') or item['lang'],
                order=meta.get('order', 0),
            )
            item['w'], item['h'] = renderer.measure_template(template, demo['parameters'])
        except Exception as e:
            item['error'] = f'{type(e).__name__}: {e}'
        items.append(item)

    items.sort(key=lambda it: (_group_sort_key(it['group']), it['order'], it['name']))
    return items


def gallery_html(renderer: RendererEngine, missing: str = '') -> str:
    data = {'demos': demo_catalog(renderer), 'missing': missing}
    # "</" would close the <script> the JSON sits in
    payload = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    with open(GALLERY_PAGE, encoding='utf-8') as f:
        return f.read().replace('__CATALOG__', payload)
