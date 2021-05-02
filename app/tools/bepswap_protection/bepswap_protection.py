# Don't forget to switch PYTHON's Path to ../../ (thorchainmonitorbot/app/)

import asyncio
import datetime
import logging
import os
from collections import defaultdict
from typing import List, Dict

from tqdm import tqdm

from services.jobs.fetch.runeyield import HomebrewLPConnector
from services.jobs.fetch.tx import TxFetcher
from services.lib.constants import NetworkIdents
from services.lib.date_utils import DAY
from services.lib.money import short_address
from services.lib.utils import load_pickle, save_pickle
from services.models.tx import ThorTx, final_liquidity, ThorTxType, cut_txs_before_previous_full_withdraw
from tools.lib.lp_common import LpAppFramework

logging.basicConfig(level=logging.INFO)

TX_CACHE_FILE = '../temp/bepswap_protection/txs_list.pickle'

PoolToTxList = Dict[str, List[ThorTx]]
UserToPoolToTxList = Dict[str, PoolToTxList]


# 1. Load all stakes/unstakes => cache them into data file
# 1.1 Filter those that older than 100 days (options since first action/since last action)
# 2. Load all pool prices at heights of these TXs
# 3. Import LP calculator and get all LP positions, calculate impermanent losses and rune compensation at current price
# 4. Export to XLS


async def get_transactions(app: LpAppFramework, cache_file):
    txs = load_pickle(cache_file)

    if txs:
        logging.info(f'Loaded {len(txs)} TXs!')
    else:
        logging.warning(f'No Txs cache! Fetching them all...')

        tx_fetcher = TxFetcher(app.deps)
        tx_fetcher.progress_tracker = tqdm(total=10)
        txs = await tx_fetcher.fetch_all_tx(liquidity_change_only=True, address=None)  # everyone!
        save_pickle(cache_file, txs)

    return txs


async def sort_txs_to_pool_and_users(txs: List[ThorTx]) -> UserToPoolToTxList:
    u2txs = defaultdict(list)
    txs.sort(key=lambda tx: tx.height_int)
    for tx in txs:
        sender = tx.sender_address
        if sender:
            u2txs[sender].append(tx)
        else:
            logging.warning(f'no sender for tx: {tx}')

    u2p2txs = {}

    for user, txs in u2txs.items():
        p2txs = defaultdict(list)
        tx: ThorTx
        for tx in txs:
            if tx.first_pool:
                p2txs[tx.first_pool].append(tx)
            else:
                logging.warning(f'no pool for tx: {tx}')

        u2p2txs[user] = p2txs

    return u2p2txs


def is_good_tx_list(txs: List[ThorTx], discard_later_ts, since_last_action=False, check_positive_lp=True) -> bool:
    if not txs:
        return False

    control_tx = txs[-1 if since_last_action else 0]  # 0 = earliest, -1 = laters
    if control_tx.date_timestamp > discard_later_ts:
        return False

    if check_positive_lp and final_liquidity(txs) <= 0:
        return False

    return True


def filter_txs(u2p2txs: UserToPoolToTxList, discard_later_ts, since_last_action=False,
               check_positive_lp=True) -> UserToPoolToTxList:
    result_u2p2txs = {}

    for address, p2txs2 in u2p2txs.items():
        result_p2txs = {}
        for pool, txs in p2txs2.items():
            prev_tx_count = len(txs)
            txs = cut_txs_before_previous_full_withdraw(txs)
            if prev_tx_count != len(txs):
                logging.debug(f'Full withdraw detected for {address = !r} at {pool = !r}, {prev_tx_count = }, '
                              f'now {len(txs) = }')

            if is_good_tx_list(txs, discard_later_ts, since_last_action, check_positive_lp):
                result_p2txs[pool] = txs

        if result_p2txs:
            result_u2p2txs[address] = result_p2txs

    return result_u2p2txs


def ensure_data_dir():
    dir_name = os.path.dirname(TX_CACHE_FILE)
    if not os.path.exists(dir_name):
        logging.warning(f'Output dir "{dir_name}" not found. I will try to make it.')
        os.makedirs(dir_name, exist_ok=True)


async def calc_impermanent_loss(app: LpAppFramework, address, pool, txs: List[ThorTx]):
    yield_report = await app.rune_yield.generate_yield_report_single_pool(address, pool, user_txs=txs)

    print()
    print(f'Pool: "{pool}" @ "{address}" {yield_report.fees.imp_loss_percent = }, {yield_report.fees.imp_loss_usd = } $')


def find_pool_with_withdraws(filter_u2p2txs: UserToPoolToTxList, start=0):
    tx: ThorTx
    i = 0
    for address, p2txs in filter_u2p2txs.items():
        if i >= start:
            for pool, txs in p2txs.items():
                for tx in txs:
                    if tx.type == ThorTxType.TYPE_WITHDRAW:
                        return address, pool, txs
        i += 1

    return None, None, None


async def debug_1_pool(app, filtered_u2p2txs):
    # address1, pool1, txs1 = find_pool_with_withdraws(filtered_u2p2txs, start=500)
    address1 = 'bnb1gatq8xrczffkwer3ulhunk65n62ck0r0pz6lz4'
    pool1 = 'BNB.TWT-8C2'
    txs1 = filtered_u2p2txs[address1][pool1]

    print(address1, pool1)

    await calc_impermanent_loss(app, address1, pool1, txs1)

    lp = final_liquidity(txs1)
    print(f'Final liquidity {pool1} @ {address1} = {lp}')


async def run_pipeline(app: LpAppFramework):
    ensure_data_dir()

    txs = await get_transactions(app, TX_CACHE_FILE)

    user_to_txs = await sort_txs_to_pool_and_users(txs)

    discard_later_ts = datetime.datetime.now().timestamp() - 100 * DAY

    filtered_u2p2txs = filter_txs(user_to_txs, discard_later_ts, since_last_action=False, check_positive_lp=True)
    print(len(filtered_u2p2txs), 'users finally.')

    for user, p2txs in tqdm(filtered_u2p2txs.items()):
        for pool, txs in p2txs.items():
            await calc_impermanent_loss(app, user, pool, txs)


async def main():
    app = LpAppFramework(HomebrewLPConnector, network=NetworkIdents.CHAOSNET_BEP2CHAIN)
    async with app:
        await run_pipeline(app)


if __name__ == '__main__':
    asyncio.run(main())
