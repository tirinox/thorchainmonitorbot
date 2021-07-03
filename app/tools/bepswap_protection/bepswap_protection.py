# Don't forget to switch PYTHON's Path to ../../ (thorchainmonitorbot/app/)

import asyncio
import datetime
import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Dict

import xlsxwriter
from tqdm import tqdm

from services.jobs.fetch.runeyield import HomebrewLPConnector
from services.jobs.fetch.tx import TxFetcher
from services.lib.constants import NetworkIdents, THOR_DIVIDER_INV
from services.lib.date_utils import DAY
from services.lib.utils import load_pickle, save_pickle
from services.models.pool_info import PoolInfo, pool_share
from services.models.tx import ThorTx, final_liquidity, ThorTxType, cut_txs_before_previous_full_withdraw
from tools.lib.lp_common import LpAppFramework

logging.basicConfig(level=logging.INFO)

TX_CACHE_FILE = '../temp/bepswap_protection/txs_list.pickle'
RESULTS_XLSX = '../temp/bepswap_protection/results_{date}.xlsx'
CUT_OFF_HEIGHT = 999_999_999_999
MIN_DAYS_LP_REQUIRED = 100

PoolToTxList = Dict[str, List[ThorTx]]
UserToPoolToTxList = Dict[str, PoolToTxList]


# 1. Load all add/withdraw => cache them into data file
# 1.1 Filter those that older than 100 days (options like: since first action/since last action)
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

    txs.sort(key=lambda tx: tx.height_int)  # make sure it's chronological order!

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


class ProtectionMode(Enum):
    SINCE_LAST_ACTION = auto()
    SINCE_LAST_DEPOSIT = auto()
    SINCE_FIRST_DEPOSIT = auto()


def has_asymmetric_add(txs: List[ThorTx], asset_only=False, rune_only=True):
    for tx in txs:
        if tx.type == ThorTxType.TYPE_ADD_LIQUIDITY:
            if asset_only and tx.sum_of_rune(in_only=True) == 0.0:
                return True
            if rune_only and tx.sum_of_asset(tx.first_pool, in_only=True) == 0.0:
                return True
    return False


# todo: filter out asymmetrical deposits
def is_eligible_transaction_list(txs: List[ThorTx], discard_later_ts, mode: ProtectionMode,
                                 check_positive_lp=True) -> bool:
    if not txs:
        return False

    if txs[-1].height_int > CUT_OFF_HEIGHT:
        return False  # exclude everyone who did something after the snapshot!

    if mode == ProtectionMode.SINCE_FIRST_DEPOSIT:
        control_tx = txs[0]
    elif mode == ProtectionMode.SINCE_LAST_ACTION:
        control_tx = txs[-1]
    elif mode == ProtectionMode.SINCE_LAST_DEPOSIT:
        # todo: test it
        control_tx = next(tx for tx in reversed(txs) if tx.type == ThorTxType.TYPE_ADD_LIQUIDITY)
    else:
        return False

    if control_tx.date_timestamp > discard_later_ts:
        return False

    if check_positive_lp and final_liquidity(txs) <= 0:
        return False

    return True


def filter_txs(u2p2txs: UserToPoolToTxList, discard_later_ts, mode: ProtectionMode,
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

            if is_eligible_transaction_list(txs, discard_later_ts, mode, check_positive_lp):
                result_p2txs[pool] = txs

        if result_p2txs:
            result_u2p2txs[address] = result_p2txs

    return result_u2p2txs


def calculate_impermanent_loss_in_rune(txs: List[ThorTx], current_pool_info: PoolInfo):
    deposited_asset = 0
    deposited_rune = 0

    for tx in txs:
        asset = tx.first_pool
        if tx.type == ThorTxType.TYPE_ADD_LIQUIDITY:
            deposited_asset += tx.sum_of_asset(asset, in_only=True)
            deposited_rune += tx.sum_of_rune(in_only=True)
        elif tx.type == ThorTxType.TYPE_WITHDRAW:
            deposited_asset -= tx.sum_of_asset(asset, out_only=True)
            deposited_rune -= tx.sum_of_rune(out_only=True)

    lp = final_liquidity(txs)

    current_rune, current_asset = pool_share(current_pool_info.balance_rune, current_pool_info.balance_asset,
                                             lp, current_pool_info.pool_units)
    current_rune *= THOR_DIVIDER_INV
    current_asset *= THOR_DIVIDER_INV

    p1 = current_rune / current_asset
    coverage = (deposited_rune - current_rune) + (deposited_asset - current_asset) * p1
    return coverage


def ensure_data_dir():
    dir_name = os.path.dirname(TX_CACHE_FILE)
    if not os.path.exists(dir_name):
        logging.warning(f'Output dir "{dir_name}" not found. I will try to make it.')
        os.makedirs(dir_name, exist_ok=True)


async def process_one_address_one_pool(app: LpAppFramework, address, pool, txs: List[ThorTx]):
    pool_info = app.deps.price_holder.find_pool(pool)

    if not pool_info:
        logging.warning(f'No pool_info for "{pool}"!')
        return 0.0

    rune_coverage = calculate_impermanent_loss_in_rune(txs, pool_info)
    return rune_coverage


def find_pool_with_withdraws(filter_u2p2txs: UserToPoolToTxList, start=0, min_withdraw=1):
    tx: ThorTx
    i = 0
    for address, p2txs in filter_u2p2txs.items():
        if i >= start:
            for pool, txs in p2txs.items():
                withdraw_count = 0
                for tx in txs:
                    if tx.type == ThorTxType.TYPE_WITHDRAW:
                        withdraw_count += 1
                    if withdraw_count >= min_withdraw:
                        return address, pool, txs
        i += 1

    return None, None, None


@dataclass
class CoverageEntry:
    address: str
    pool: str
    rune_protection: float
    usd_protection: float
    last_add_date: datetime.datetime
    has_rune_only_adds: bool
    has_asset_only_adds: bool


def save_results(xls_path, results: List[CoverageEntry]):
    workbook = xlsxwriter.Workbook(xls_path)
    worksheet = workbook.add_worksheet('IL Protection')

    date_format = workbook.add_format({'num_format': 'dd/mm/yy hh:mm'})
    center_format = workbook.add_format({'align': 'center'})
    money_format = workbook.add_format({'num_format': '#,##0.00'})
    header_format = workbook.add_format({'bold': True, 'font_size': 14})

    worksheet.freeze_panes(2, 0)

    now = datetime.datetime.now()

    worksheet.write('A1', 'Date:')
    worksheet.write('B1', str(now))

    worksheet.write('A2', 'Address', header_format)
    worksheet.write('B2', 'Pool', header_format)
    worksheet.write('C2', 'Coverage, Rune', header_format)
    worksheet.write('D2', 'Coverage, USD', header_format)
    worksheet.write('E2', 'Last Add date', header_format)
    worksheet.write('F2', 'Days', header_format)
    worksheet.write('G2', 'Rune only add?', header_format)
    worksheet.write('H2', 'Asset only adds?', header_format)

    row = 0
    for row, entry in enumerate(results, start=3):
        worksheet.write(f'A{row}', entry.address)
        worksheet.write(f'B{row}', entry.pool)
        worksheet.write_number(f'C{row}', entry.rune_protection, money_format)
        worksheet.write_number(f'D{row}', entry.usd_protection, money_format)
        worksheet.write_datetime(f'E{row}', entry.last_add_date, date_format)

        days = int(round((now - entry.last_add_date).total_seconds() / DAY))
        worksheet.write_number(f'F{row}', days, center_format)

        worksheet.write(f'G{row}', "v" if entry.has_rune_only_adds else " ", center_format)
        worksheet.write(f'H{row}', "v" if entry.has_asset_only_adds else " ", center_format)

    if row:
        worksheet.write_formula(f'C{row + 1}', f'=SUM(C3:C{row})')
        worksheet.write_formula(f'D{row + 1}', f'=SUM(D3:D{row})')
        worksheet.write(f'A{row + 1}', f'Sum:')

    worksheet.set_column(0, 0, 50)
    worksheet.set_column(1, 1, 17)
    worksheet.set_column(2, 3, 20)
    worksheet.set_column(4, 4, 18)
    worksheet.set_column(5, 5, 12)
    worksheet.set_column(6, 7, 18)

    workbook.close()


def last_add_date(txs: List[ThorTx]):
    cur_date = 0
    for tx in txs:
        if tx.type == ThorTxType.TYPE_ADD_LIQUIDITY:
            if tx.date_timestamp > cur_date:
                cur_date = tx.date_timestamp

    # convert to xls
    return datetime.datetime.fromtimestamp(cur_date)


async def run_pipeline(app: LpAppFramework):
    ensure_data_dir()

    mode = ProtectionMode.SINCE_LAST_DEPOSIT

    txs = await get_transactions(app, TX_CACHE_FILE)

    user_to_txs = await sort_txs_to_pool_and_users(txs)

    discard_later_ts = datetime.datetime.now().timestamp() - MIN_DAYS_LP_REQUIRED * DAY
    filtered_u2p2txs = filter_txs(user_to_txs, discard_later_ts, mode, check_positive_lp=True)

    print(len(filtered_u2p2txs), 'users finally.')

    results = []

    for user, p2txs in tqdm(filtered_u2p2txs.items()):
        pools = sorted(p2txs.keys())
        for pool in pools:
            txs = p2txs[pool]
            rune_coverage = await process_one_address_one_pool(app, user, pool, txs)
            if rune_coverage > 0:
                results.append(CoverageEntry(
                    address=user,
                    pool=pool,
                    rune_protection=rune_coverage,
                    usd_protection=rune_coverage * app.deps.price_holder.usd_per_rune,
                    last_add_date=last_add_date(txs),
                    has_rune_only_adds=has_asymmetric_add(txs, rune_only=True),
                    has_asset_only_adds=has_asymmetric_add(txs, asset_only=True),
                ))

    date_str = datetime.datetime.now().strftime("%b-%d-%Y_%H-%M-%S")
    xlsx_filename = RESULTS_XLSX.format(date=date_str)
    save_results(xlsx_filename, results)


async def main():
    app = LpAppFramework(HomebrewLPConnector, network=NetworkIdents.CHAOSNET_BEP2CHAIN)
    async with app:
        await run_pipeline(app)


if __name__ == '__main__':
    asyncio.run(main())

# -----------------------------------------------------------------

async def debug_1_pool(app, filtered_u2p2txs):
    # address1, pool1, txs1 = find_pool_with_withdraws(filtered_u2p2txs, start=500)
    address1 = 'bnb1gatq8xrczffkwer3ulhunk65n62ck0r0pz6lz4'
    pool1 = 'BNB.TWT-8C2'
    txs1 = filtered_u2p2txs[address1][pool1]

    print(address1, pool1)

    await process_one_address_one_pool(app, address1, pool1, txs1)

    lp = final_liquidity(txs1)
    print(f'Final liquidity {pool1} @ {address1} = {lp}')
