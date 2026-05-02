import asyncio
import os
from pprint import pprint

from comm.localization.eng_base import BaseLocalization
from comm.localization.languages import Language
from comm.localization.manager import LocalizationManager
from comm.picture.supply_picture import SupplyPictureGenerator
from jobs.fetch.circulating import RuneCirculatingSupplyFetcher
from jobs.fetch.net_stats import NetworkStatisticsFetcher
from lib.constants import RUNE_DENOM
from lib.date_utils import today_str
from lib.draw_utils import img_to_bio
from lib.utils import load_pickle, save_pickle
from models.circ_supply import RuneCirculatingSupply
from models.mimir_naming import MIMIR_KEY_MAX_RUNE_SUPPLY
from models.price import RuneMarketInfo
from notify.channel import BoardMessage
from tools.debug.dbg_discord import debug_prepare_discord_bot
from tools.lib.lp_common import LpAppFramework

SUPPLY_CACHE_PATH = '../temp/data_for_sup_pic_v12.pickle'
ADR23_SEARCH_LOWER_BLOCK = 24_000_000
ADR23_SEARCH_UPPER_BLOCK = 26_000_000
ADR23_PATCH_BURN_THRESHOLD_RUNE = 60_000_000


def _interesting_constant_subset(values: dict, tokens=('ADR', 'BURN', 'RUNE', 'SUPPLY', 'MAX')):
    if not values:
        return {}
    return {
        k: v for k, v in sorted(values.items())
        if any(token in k.upper() for token in tokens)
    }


async def _get_supply_snapshot(app: LpAppFramework, height: int):
    thor = app.deps.thor_connector

    supply_raw, mimir, constants = await asyncio.gather(
        thor.query_supply(height=height),
        thor.query_mimir(height=height),
        thor.query_constants(height=height),
    )

    total_supply = int(RuneCirculatingSupplyFetcher.get_specific_denom_amount(supply_raw, RUNE_DENOM))
    max_supply_raw = int(mimir.get(MIMIR_KEY_MAX_RUNE_SUPPLY, 0) or 0) if mimir else 0
    max_supply = max_supply_raw // 10 ** 8
    supply_info = RuneCirculatingSupply(total=total_supply, maximum=max_supply or total_supply, holders={})

    return {
        'height': int(height),
        'total_supply': total_supply,
        'max_supply_raw': max_supply_raw,
        'max_supply': max_supply,
        'adr23_burnt_rune': int(supply_info.adr23_burnt_rune),
        'mimir_constants': dict(mimir.constants) if mimir and mimir.constants else {},
        'network_constants': dict(constants.constants) if constants and constants.constants else {},
    }


async def _get_block_time_str(app: LpAppFramework, height: int):
    raw = await app.deps.thor_connector.query_tendermint_block_raw(height)
    try:
        return raw['result']['block']['header']['time']
    except (TypeError, KeyError):
        return 'unknown'


def _print_supply_snapshot(label: str, snap: dict):
    print(
        f'{label}: '
        f'block={snap["height"]:,}, '
        f'total={snap["total_supply"]:,}, '
        f'max_raw={snap["max_supply_raw"]:,}, '
        f'max={snap["max_supply"]:,}, '
        f'adr23={snap["adr23_burnt_rune"]:,}'
    )


def _print_max_supply_delta(label: str, prev_snap: dict, curr_snap: dict):
    delta_raw = prev_snap['max_supply_raw'] - curr_snap['max_supply_raw']
    print(
        f'{label}: '
        f'prev_block={prev_snap["height"]:,}, '
        f'curr_block={curr_snap["height"]:,}, '
        f'delta_raw={delta_raw:,}, '
        f'delta_rune={delta_raw / 10 ** 8:,.8f}'
    )


async def dbg_find_adr23_burn_block(app: LpAppFramework,
                                    start_height: int = ADR23_SEARCH_LOWER_BLOCK,
                                    end_height: int = ADR23_SEARCH_UPPER_BLOCK,
                                    patch_burn_threshold_rune: int = ADR23_PATCH_BURN_THRESHOLD_RUNE):
    deps = app.deps
    last_block = await deps.last_block_cache.get_thor_block()
    if not last_block:
        raise RuntimeError('Cannot get last THORChain block')

    start_height = int(start_height)
    end_height = int(end_height)
    if start_height >= end_height:
        raise ValueError(f'Invalid bracket: {start_height = } must be below {end_height = }')
    if end_height > last_block:
        raise ValueError(f'end_height={end_height} must be <= last_block={last_block}')

    patch_burn_threshold_raw = int(patch_burn_threshold_rune) * 10 ** 8

    left_snap = await _get_supply_snapshot(app, start_height)
    right_snap = await _get_supply_snapshot(app, end_height)
    _print_supply_snapshot('left bracket', left_snap)
    _print_supply_snapshot('right bracket', right_snap)

    baseline_max_raw = left_snap['max_supply_raw']
    bracket_drop_raw = baseline_max_raw - right_snap['max_supply_raw']
    if bracket_drop_raw < patch_burn_threshold_raw:
        raise ValueError(
            f'Known bracket does not contain the expected big burn: '
            f'drop={bracket_drop_raw:,} raw ({bracket_drop_raw / 10 ** 8:,.8f} RUNE), '
            f'threshold={patch_burn_threshold_raw:,} raw ({patch_burn_threshold_rune:,} RUNE)'
        )

    left_height = start_height
    right_height = end_height

    print('\nBinary search for the first block where the large MAXRUNESUPPLY drop becomes visible...')
    while right_height - left_height > 1:
        mid = (left_height + right_height) // 2
        mid_snap = await _get_supply_snapshot(app, mid)
        mid_drop_raw = baseline_max_raw - mid_snap['max_supply_raw']
        print(
            f'mid block={mid:,}, '
            f'max_raw={mid_snap["max_supply_raw"]:,}, '
            f'drop_raw={mid_drop_raw:,}, '
            f'total={mid_snap["total_supply"]:,}, '
            f'adr23={mid_snap["adr23_burnt_rune"]:,}'
        )

        if mid_drop_raw >= patch_burn_threshold_raw:
            right_height = mid
            right_snap = mid_snap
        else:
            left_height = mid
            left_snap = mid_snap

    prev_snap = await _get_supply_snapshot(app, right_height - 1)
    burn_snap = await _get_supply_snapshot(app, right_height)
    burn_time = await _get_block_time_str(app, right_height)

    print('\nCandidate boundary for the patch burn:')
    _print_supply_snapshot('prev block', prev_snap)
    _print_supply_snapshot('burn block', burn_snap)
    print(f'block_time={burn_time}')
    _print_max_supply_delta('boundary max drop', prev_snap, burn_snap)
    print(f'total drop at boundary={prev_snap["total_supply"] - burn_snap["total_supply"]:,}')

    print('\nInteresting Mimir keys near the burn block:')
    pprint(_interesting_constant_subset(burn_snap['mimir_constants']))

    print('\nInteresting network constants near the burn block:')
    pprint(_interesting_constant_subset(burn_snap['network_constants']))

    print('\nSmall window around the candidate block:')
    window_snaps = []
    for height in range(max(start_height, right_height - 2), min(end_height, right_height + 2) + 1):
        snap = prev_snap if height == prev_snap['height'] else burn_snap if height == burn_snap['height'] else await _get_supply_snapshot(app, height)
        window_snaps.append(snap)
        _print_supply_snapshot('window', snap)

    print('\nNeighbor deltas inside the local window:')
    for prev_item, curr_item in zip(window_snaps, window_snaps[1:]):
        _print_max_supply_delta('window delta', prev_item, curr_item)

    return {
        'prev_block': prev_snap,
        'burn_block': burn_snap,
        'burn_time': burn_time,
        'boundary_drop': prev_snap['total_supply'] - burn_snap['total_supply'],
    }
#
# @json_cached_to_file_async("../temp/net_stats1.json")
# async def get_network_stats(app: LpAppFramework):
#     ns_fetcher = NetworkStatisticsFetcher(app.deps)
#     data = await ns_fetcher.fetch()
#     return dataclasses.asdict(data)


async def get_supply_pic(app, cached=True):
    loc_man: LocalizationManager = app.deps.loc_man
    loc = loc_man.get_from_lang(Language.ENGLISH)

    if cached:
        try:
            net_stats, rune_market_info = load_pickle(SUPPLY_CACHE_PATH)
        except Exception as e:
            print(e)
            net_stats, rune_market_info = await debug_get_rune_market_data(app)
            save_pickle(SUPPLY_CACHE_PATH, (net_stats, rune_market_info))
    else:
        net_stats, rune_market_info = await debug_get_rune_market_data(app)

    # prev supply
    rune_market_info.prev_supply_info = rune_market_info.supply_info.distorted()
    # rune_market_info.prev_supply_info = rune_market_info.supply_info.zero()
    # rune_market_info.prev_supply_info = None

    pic_gen = SupplyPictureGenerator(loc, rune_market_info.supply_info, net_stats, rune_market_info.prev_supply_info)

    return await pic_gen.get_picture()


async def debug_get_rune_market_data(app):
    d = app.deps

    await app.deps.pool_fetcher.fetch()

    # ns_raw = await get_network_stats(app)
    # ns = NetworkStats(**ns_raw)

    fetcher_stats = NetworkStatisticsFetcher(d)
    d.net_stats = await fetcher_stats.fetch()

    rune_market_info: RuneMarketInfo = await d.market_info_cache.get()
    return d.net_stats, rune_market_info


def save_and_show_supply_pic(pic, show=True):
    filepath = '../temp/supply.png'
    with open(filepath, 'wb') as f:
        pic_bio = img_to_bio(pic, os.path.basename(filepath))
        f.write(pic_bio.getbuffer())

    if show:
        os.system(f'open "{filepath}"')


async def post_supply_to_discord(app: LpAppFramework, pic):
    await debug_prepare_discord_bot(app)

    async def supply_pic_gen(loc: BaseLocalization):
        return BoardMessage.make_photo(pic, loc.SUPPLY_PIC_CAPTION, f'rune_supply_{today_str()}.png')

    await app.deps.broadcaster.broadcast_to_all("debug_supply", supply_pic_gen)

    await asyncio.sleep(10)


async def debug_network_stats(app: LpAppFramework):
    ns_fetcher = NetworkStatisticsFetcher(app.deps)
    data = await ns_fetcher.fetch()
    pprint(data)


async def run():
    app = LpAppFramework()
    async with app:
        # await app.deps.pool_fetcher.fetch()

        await dbg_find_adr23_burn_block(app)

        # pic, _ = await get_supply_pic(app, cached=True)
        # save_and_show_pic(pic, show=True, name='supply')

        # await post_supply_to_discord(app, pic)
        # await debug_network_stats(app)


if __name__ == '__main__':
    asyncio.run(run())
