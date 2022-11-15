import logging
from collections import defaultdict
from typing import List

from services.lib.constants import thor_to_float
from services.lib.utils import WithLogger
from services.models.tx import ThorCoin, ThorTx, ThorMetaSwap, ThorMetaAddLiquidity, ThorSubTx


class AffiliateTXMerger(WithLogger):
    def __init__(self):
        super().__init__()

    MAX_ALLOWED_AFFILIATE_FEE_RATIO = 0.2  # in fact, 0.15 but we take extra

    def calc_affiliate_fee_floats(self, amount_a, amount_b):
        if amount_a == amount_b == 0.0:
            self.logger.error(f'Both amounts are zero!')
            return 0.0
        return min(amount_a, amount_b) / max(amount_a, amount_b)

    def calc_affiliate_fee_from_coins(self, a: ThorCoin, b: ThorCoin):
        amount_a, amount_b = thor_to_float(a.amount), thor_to_float(b.amount)
        return self.calc_affiliate_fee_floats(amount_a, amount_b)

    def calc_affiliate_fee_rate(self, tx_a: ThorTx, tx_b: ThorTx):
        if tx_a.meta_add and tx_b.meta_add:
            a_fee = self.calc_affiliate_fee_floats(tx_a.meta_add.liquidity_units_int, tx_b.meta_add.liquidity_units_int)
        elif tx_a.meta_swap and tx_b.meta_swap:
            a_fee = max(tx_a.meta_swap.affiliate_fee, tx_b.meta_swap.affiliate_fee)
        else:
            # old method
            in_a, in_b = tx_a.first_input_tx, tx_b.first_input_tx
            if not in_a or not in_b or not in_a.coins or not in_b.coins:
                self.logger.error(f'Empty input Txs or no coins')
                return 0.0

            coins_a, coins_b = in_a.none_rune_coins, in_b.none_rune_coins
            if coins_a and coins_b:
                coin_a, coin_b = coins_a[0], coins_b[0]
                if coin_a.asset != coin_b.asset:
                    self.logger.error(f'Coin asset mismatch: {coin_a.asset} vs {coin_b.asset}!')
                    return 0.0
                return self.calc_affiliate_fee_from_coins(coin_a, coin_b)

            coin_a, coin_b = in_a.rune_coin, in_b.rune_coin
            a_fee = self.calc_affiliate_fee_from_coins(coin_a, coin_b)

        if a_fee > self.MAX_ALLOWED_AFFILIATE_FEE_RATIO:
            self.logger.error(f'Affiliate fee is too big to be true: {a_fee = } > 0.15')
            return 0.0
        else:
            return a_fee

    def merge_same_txs(self, tx1: ThorTx, tx2: ThorTx) -> ThorTx:
        if tx1.type != tx2.type:
            self.logger.warning('Same tx data mismatch, continuing...')
            return tx1

        result_tx, other_tx = tx1, tx2

        try:
            result_tx.affiliate_fee = self.calc_affiliate_fee_rate(result_tx, other_tx)

            result_tx.in_tx = self.merge_sub_txs(other_tx.in_tx, result_tx.in_tx)
            result_tx.out_tx = self.merge_sub_txs(other_tx.out_tx, result_tx.out_tx)

            result_tx.pools = result_tx.pools if len(result_tx.pools) > len(other_tx.pools) else other_tx.pools

            # merge meta
            result_tx.meta_swap = ThorMetaSwap.merge_two(result_tx.meta_swap, other_tx.meta_swap)
            result_tx.meta_add = ThorMetaAddLiquidity.merge_two(result_tx.meta_add, other_tx.meta_add)

            result_tx.__post_init__()  # explicit call to refresh computed fields

        except (IndexError, TypeError, ValueError, AssertionError):
            logging.error(f'Cannot merge: {result_tx} and {other_tx}!')

        return result_tx

    @staticmethod
    def merge_sub_txs(other_tx: List[ThorSubTx], result_tx: List[ThorSubTx]) -> List[ThorSubTx]:
        # collect (TXID, address) for each input asset name for both Txs
        hash_addr_tracker = {}
        for tx in [*result_tx, *other_tx]:
            for coin in tx.coins:
                if coin.asset not in hash_addr_tracker:
                    hash_addr_tracker[coin.asset] = tx.tx_id, tx.address
                else:
                    old_id, old_address = hash_addr_tracker[coin.asset]
                    hash_addr_tracker[coin.asset] = (old_id or tx.tx_id), (old_address or tx.address)

        # merge all same coins and put them in the dictionary using asset-name as key
        merge_coins_dic = {}
        all_coins = [
            *(c for tx in result_tx for c in tx.coins),
            *(c for tx in other_tx for c in tx.coins)
        ]
        for coin in all_coins:
            coin: ThorCoin
            if coin.asset not in merge_coins_dic:
                merge_coins_dic[coin.asset] = coin
            else:
                merge_coins_dic[coin.asset] = ThorCoin.merge_two(merge_coins_dic[coin.asset], coin)

        # reconstruct inputs list
        new_input_transactions = []
        for asset, (tx_id, address) in hash_addr_tracker.items():
            coin = merge_coins_dic[asset]
            new_input_transactions.append(
                ThorSubTx(
                    address, [coin], tx_id
                )
            )
        return new_input_transactions

    def merge_affiliate_txs(self, txs: List[ThorTx]):
        len_before = len(txs)
        same_tx_id_set = defaultdict(list)
        for tx in txs:
            tx.sort_inputs_by_first_asset()
            h = tx.first_input_tx_hash
            if h:
                same_tx_id_set[h].append(tx)

        for h, same_tx_list in same_tx_id_set.items():
            if len(same_tx_list) == 2:
                tx1, tx2 = same_tx_list
                if tx1.deep_eq(tx2):  # same txs => ignore
                    continue
                else:
                    result_tx = self.merge_same_txs(tx1, tx2)
                    txs = list(filter(lambda a_tx: a_tx.first_input_tx_hash != h, txs))
                    txs.append(result_tx)
            elif len(same_tx_list) > 2:
                self.logger.error(f'> 2 same hash TX ({h})! It is strange! Ignoring them all')
                continue

        txs.sort(key=lambda tx: tx.height_int, reverse=True)

        if len_before > len(txs):
            self.logger.info(f'Some TXS were merged: {len_before} => {len(txs)}')

        return txs
