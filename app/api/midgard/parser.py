import logging
from typing import NamedTuple, List, Optional

from models.memo import ActionType, is_action
from models.pool_info import PoolInfoHistoricEntry, PoolInfoMap, PoolInfo
from models.pool_member import PoolMemberDetails
from models.tx import ThorAction, ThorSubTx, ThorMetaSwap, ThorMetaRefund, ThorMetaWithdraw, \
    ThorMetaAddLiquidity

logger = logging.getLogger(__name__)


class TxParseResult(NamedTuple):
    total_count: int = 0
    txs: List[ThorAction] = None
    tx_count_unfiltered: int = 0
    network_id: str = ''
    next_page_token: str = ''
    prev_page_token: str = ''

    @property
    def tx_count(self):
        return len(self.txs)

    @property
    def first(self) -> Optional[ThorAction]:
        return self.txs[0] if self.txs else None


class MidgardParserV2:
    """
    Midgard V2 + Multi-chain network
    """

    def __init__(self, network_id):
        self.network_id = network_id

    def safe_parse_raw_batch(self, raw_txs):
        for r in raw_txs:
            try:
                yield self.parse_one_tx(r)
            except (IndexError, ValueError, KeyError) as e:
                logger.error(f'failed to parse TX. error: {e!r}; json = {r}')
                continue

    def parse_one_tx(self, r):
        status = r.get('status', '').lower()
        block_height = r.get('height', '0')
        tx_type = r.get('type')
        pools = r.get('pools', [])
        date = r.get('date', '0')
        metadata = r.get('metadata', {})

        in_tx_list = [ThorSubTx.parse(rt) for rt in r.get('in', [])]
        out_tx_list = [ThorSubTx.parse(rt) for rt in r.get('out', [])]

        meta_add = ThorMetaAddLiquidity.parse(
            metadata.get('addLiquidity', {})) if is_action(tx_type, ActionType.ADD_LIQUIDITY) else None
        meta_withdraw = ThorMetaWithdraw.parse(
            metadata.get('withdraw', {})) if is_action(tx_type, ActionType.WITHDRAW) else None
        meta_swap = ThorMetaSwap.parse(metadata.get('swap', {})) if is_action(tx_type, ActionType.SWAP) else None
        meta_refund = ThorMetaRefund.parse(
            metadata.get('refund', {})) if is_action(tx_type, ActionType.REFUND) else None

        return ThorAction(
            int(date), int(block_height), status, tx_type,
            pools, in_tx_list, out_tx_list,
            meta_add, meta_withdraw, meta_swap, meta_refund
        )

    def parse_tx_response(self, response: dict) -> TxParseResult:
        raw_txs = response.get('actions', [])
        count = int(response.get('count', 0))
        txs = list(self.safe_parse_raw_batch(raw_txs))
        meta = response.get('meta', {})
        return TxParseResult(
            count, txs, len(raw_txs), network_id=self.network_id,
            next_page_token=meta.get('nextPageToken', ''),
            prev_page_token=meta.get('prevPageToken', '')
        )

    def parse_historic_pool_items(self, response: dict) -> List[PoolInfoHistoricEntry]:
        results = []
        intervals = response.get('intervals', [])
        for j in intervals:
            asset_depth = int(j.get('assetDepth', '0'))
            rune_depth = int(j.get('runeDepth', '0'))
            asset_price = asset_depth / rune_depth if rune_depth else 0.0
            results.append(PoolInfoHistoricEntry(
                asset_depth=asset_depth,
                rune_depth=rune_depth,
                units=int(j.get('units', 0)),  # total liquidity units!
                synth_units=int(j.get('synthUnits', 0)),
                liquidity_units=int(j.get('liquidityUnits', 0)),
                asset_price=asset_price,
                asset_price_usd=float(j.get('assetPriceUSD', '0')),
                timestamp=int(j.get('endTime', 0))
            ))
        return results

    @staticmethod
    def parse_pool_member_details(response, address='') -> List[PoolMemberDetails]:
        results = []
        if isinstance(response, str):
            return results
        for j in response.get('pools', []):
            results.append(PoolMemberDetails.from_json(j))
        return results

    @staticmethod
    def parse_pool_membership(response) -> List[PoolMemberDetails]:
        if not response:
            return []
        pools = response.get('pools', [])
        return [PoolMemberDetails.from_json(p) for p in pools if 'pool' in p]

    def parse_pool_info(self, response) -> PoolInfoMap:
        pm = {}
        for j in response:
            asset = j.get('asset')
            pm[asset] = PoolInfo(
                asset=asset,
                balance_asset=int(j.get('assetDepth', 0)),
                balance_rune=int(j.get('runeDepth', 0)),
                pool_units=int(j.get('liquidityUnits', 0)),
                status=str(j.get('status', '')).lower(),
                # rune_per_asset=float(j.get('assetPrice', 0.0)),
                usd_per_asset=float(j.get('assetPriceUSD', 0.0)),
                pool_apy=float(j.get('poolAPY', 0.0)) * 100.0,
                synth_supply=int(j.get('synthSupply', 0)),
                synth_units=int(j.get('synthUnits', 0)),
                units=int(j.get('units', 0)),
                volume_24h=int(j.get('volume24h', 0)),
                savers_units=int(j.get('saversUnits', 0)),
                savers_depth=int(j.get('saversDepth', 0)),
                savers_apr=float(j.get('saversAPR', 0)),
                pool_apr=float(j.get('annualPercentageRate', 0)) * 100.0,
            )
        return pm


def get_parser_by_network_id(network_id) -> MidgardParserV2:
    return MidgardParserV2(network_id)
