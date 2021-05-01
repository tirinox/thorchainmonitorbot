# Don't forget to switch PYTHON's Path to ../../ (thorchainmonitorbot/app/)

import asyncio
import datetime
import json
import logging
import os
from collections import defaultdict
from typing import List, Dict

from tqdm import tqdm

from services.jobs.fetch.runeyield import HomebrewLPConnector
from services.jobs.fetch.tx import TxFetcher
from services.lib.constants import NetworkIdents
from services.lib.date_utils import DAY
from services.lib.utils import load_pickle, save_pickle
from services.models.tx import ThorTx, ThorTxType
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


def final_liquidity(txs: List[ThorTx]):
    lp = 0
    for tx in txs:
        if tx.type == ThorTxType.TYPE_ADD_LIQUIDITY:
            lp += tx.meta_add.liquidity_units_int
        elif tx.type == ThorTxType.TYPE_WITHDRAW:
            lp += tx.meta_withdraw.liquidity_units_int

    if lp == 0 and txs:
        logging.debug(f'lp = 0 for {txs[0].sender_address} in {txs[0].first_pool}')

    return lp


def is_good_tx_list(txs: List[ThorTx], discard_later_ts, since_last_action=False, check_positive_lp=True) -> bool:
    if txs:
        control_tx = txs[-1 if since_last_action else 0]
        if control_tx.date_timestamp > discard_later_ts:
            return False

        if check_positive_lp and final_liquidity(txs) <= 0:
            return False

        return True
    else:
        return False


def filter_txs(u2p2txs: UserToPoolToTxList, discard_later_ts, since_last_action=False,
               check_positive_lp=True) -> UserToPoolToTxList:
    result_u2p2txs = {}

    for address, p2txs2 in u2p2txs.items():
        result_p2txs = {}
        for pool, txs in p2txs2.items():
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


async def run_pipeline(app: LpAppFramework):
    ensure_data_dir()

    txs = await get_transactions(app, TX_CACHE_FILE)

    user_to_txs = await sort_txs_to_pool_and_users(txs)

    discard_later_ts = datetime.datetime.now().timestamp() - 100 * DAY

    filter_u2p2txs = filter_txs(user_to_txs, discard_later_ts, since_last_action=False, check_positive_lp=True)

    print(len(filter_u2p2txs), 'users finally.')


async def main():
    app = LpAppFramework(HomebrewLPConnector, network=NetworkIdents.CHAOSNET_BEP2CHAIN)
    async with app:
        await run_pipeline(app)


if __name__ == '__main__':
    asyncio.run(main())
