import logging
from abc import ABCMeta, abstractmethod
from typing import NamedTuple, List, Dict

from services.lib.constants import NetworkIdents
from services.models.last_block import LastBlock
from services.models.pool_info import PoolInfoHistoricEntry, PoolInfoMap, PoolInfo
from services.models.pool_member import PoolMemberDetails
from services.models.tx import ThorTx, ThorTxType, ThorSubTx, ThorMetaSwap, ThorMetaRefund, ThorMetaWithdraw, \
    ThorMetaAddLiquidity

logger = logging.getLogger(__name__)


class TxParseResult(NamedTuple):
    total_count: int = 0
    txs: List[ThorTx] = None
    tx_count_unfiltered: int = 0
    network_id: str = ''

    @property
    def tx_count(self):
        return len(self.txs)


class MidgardParserBase(metaclass=ABCMeta):
    def __init__(self, network_id):
        self.network_id = network_id

    @abstractmethod
    def parse_tx_response(self, response: dict) -> TxParseResult:
        ...

    @abstractmethod
    def parse_one_tx(self, r):
        ...

    def safe_parse_raw_batch(self, raw_txs):
        for r in raw_txs:
            try:
                yield self.parse_one_tx(r)
            except (IndexError, ValueError, KeyError) as e:
                logger.error(f'failed to parse TX. error: {e!r}; json = {r}')
                continue

    @abstractmethod
    def parse_historic_pool_items(self, response: dict) -> List[PoolInfoHistoricEntry]:
        ...

    @abstractmethod
    def parse_pool_member_details(self, response, address='') -> List[PoolMemberDetails]:
        ...

    @abstractmethod
    def parse_pool_membership(self, response) -> List[str]:
        ...

    @abstractmethod
    def parse_last_block(self, response) -> Dict[str, LastBlock]:
        ...

    @abstractmethod
    def parse_pool_info(self, response) -> PoolInfoMap:
        ...


class MidgardParserV1(MidgardParserBase):
    """
    Midgard V1 + Single chain BEP Swap network
    """

    def parse_pool_info(self, response) -> PoolInfoMap:
        pass

    @staticmethod
    def fix_tx_type(tx_type):
        if tx_type == ThorTxType.OLD_TYPE_UNSTAKE:
            return ThorTxType.TYPE_WITHDRAW
        elif tx_type == ThorTxType.OLD_TYPE_DOUBLE_SWAP:
            return ThorTxType.TYPE_SWAP
        elif tx_type == ThorTxType.OLD_TYPE_STAKE:
            return ThorTxType.TYPE_ADD_LIQUIDITY
        else:
            return tx_type

    def parse_one_tx(self, r):
        status = r.get('status', '').lower()
        tx_type_orig = r.get('type')
        tx_type = self.fix_tx_type(tx_type_orig)

        height = r.get('height', '0')
        date = str(int(r.get('date')) * 1_000_000_000)

        pool = r.get('pool', '')
        pools = [pool] if pool and pool != '.' else []

        in_tx_list = [ThorSubTx.parse(
            r.get('in', [])
        )]
        out_tx_list = [ThorSubTx.parse(rt) for rt in r.get('out', [])]

        meta_add = None
        meta_withdraw = None
        meta_swap = None
        meta_refund = None

        events = r.get('events', {})
        options = r.get('options', {})

        if tx_type == ThorTxType.TYPE_SWAP:
            if tx_type_orig == ThorTxType.OLD_TYPE_DOUBLE_SWAP:
                pools.append(out_tx_list[0].first_asset)
            meta_swap = ThorMetaSwap(
                liquidity_fee=events.get('fee', '0'),
                network_fees=[],
                trade_slip=str(float(events.get('slip', '0')) * 1e4),
                trade_target=options.get('priceTarget', '0')
            )
        elif tx_type == ThorTxType.TYPE_REFUND:
            meta_refund = ThorMetaRefund(
                reason=options.get('reason', ''),
                network_fees=[]
            )
        elif tx_type == ThorTxType.TYPE_WITHDRAW:
            meta_withdraw = ThorMetaWithdraw(
                asymmetry=options.get('asymmetry', '0'),
                basis_points=options.get('withdrawBasisPoints', '0'),
                liquidity_units=events.get('stakeUnits', '0'),
                network_fees=[]
            )
        elif tx_type == ThorTxType.TYPE_ADD_LIQUIDITY:
            meta_add = ThorMetaAddLiquidity(
                liquidity_units=events.get('stakeUnits', '0'),
            )

        return ThorTx(
            date, height, status, tx_type, pools, in_tx_list, out_tx_list,
            meta_add, meta_withdraw, meta_swap, meta_refund
        )

    def parse_tx_response(self, response: dict) -> TxParseResult:
        raw_txs = response.get('txs', [])
        txs = list(self.safe_parse_raw_batch(raw_txs))
        count = int(response.get('count', 0))
        return TxParseResult(count, txs, len(raw_txs), network_id=self.network_id)

    def parse_historic_pool_items(self, response: dict) -> List[PoolInfoHistoricEntry]:
        results = []
        for j in response:
            asset_depth = int(j.get('assetDepth', '0'))
            rune_depth = int(j.get('runeDepth', '0'))
            results.append(PoolInfoHistoricEntry(
                asset_depth=asset_depth,
                rune_depth=rune_depth,
                liquidity_units=0,
                asset_price=asset_depth / rune_depth,
                asset_price_usd=0.0,
                timestamp=int(j.get('time', 0))
            ))
        return results

    def parse_pool_member_details(self, response, address='') -> List[PoolMemberDetails]:
        results = []
        for j in response:
            results.append(PoolMemberDetails(
                asset_added=int(j.get('assetStaked', 0)),
                asset_address=address,
                asset_withdrawn=int(j.get('assetWithdrawn', 0)),
                date_first_added=int(j.get('dateFirstStaked', 0)),
                date_last_added=int(j.get('heightLastStaked', 0)),
                liquidity_units=int(j.get('units', 0)),
                pool=j.get('asset', ''),
                rune_added=int(j.get('runeStaked', 0)),
                rune_withdrawn=int(j.get('runeWithdrawn', 0)),
                run_address=address
            ))
        return results

    def parse_pool_membership(self, response) -> List[str]:
        return response.get('poolsArray', [])

    def parse_last_block(self, response) -> Dict[str, LastBlock]:
        chain = response.get('chain', '')
        return {
            chain: LastBlock(
                chain,
                last_observed_in=int(response.get('lastobservedin', 0)),
                last_signed_out=int(response.get('lastsignedout', 0)),
                thorchain=int(response.get('thorchain', 0))
            )
        }


class MidgardParserV2(MidgardParserBase):
    """
    Midgard V2 + Multi-chain network
    """

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
            metadata.get('addLiquidity', {})) if tx_type == ThorTxType.TYPE_ADD_LIQUIDITY else None
        meta_withdraw = ThorMetaWithdraw.parse(
            metadata.get('withdraw', {})) if tx_type == ThorTxType.TYPE_WITHDRAW else None
        meta_swap = ThorMetaSwap.parse(metadata.get('swap', {})) if tx_type == ThorTxType.TYPE_SWAP else None
        meta_refund = ThorMetaRefund.parse(
            metadata.get('refund', {})) if tx_type == ThorTxType.TYPE_REFUND else None

        return ThorTx(
            date, block_height, status, tx_type,
            pools, in_tx_list, out_tx_list,
            meta_add, meta_withdraw, meta_swap, meta_refund
        )

    def parse_tx_response(self, response: dict) -> TxParseResult:
        raw_txs = response.get('actions', [])
        count = int(response.get('count', 0))
        txs = list(self.safe_parse_raw_batch(raw_txs))
        return TxParseResult(count, txs, len(raw_txs), network_id=self.network_id)

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
                liquidity_units=0,
                asset_price=asset_price,
                asset_price_usd=float(j.get('assetPriceUSD', '0')),
                timestamp=int(j.get('endTime', 0))
            ))
        return results

    def parse_pool_member_details(self, response, address='') -> List[PoolMemberDetails]:
        results = []
        for j in response.get('pools', []):
            results.append(PoolMemberDetails(
                asset_added=int(j.get('assetAdded', 0)),
                asset_address=j.get('assetAddress', ''),
                asset_withdrawn=int(j.get('assetWithdrawn', 0)),
                date_first_added=int(j.get('dateFirstAdded', 0)),
                date_last_added=int(j.get('dateLastAdded', 0)),
                liquidity_units=int(j.get('liquidityUnits', 0)),
                pool=j.get('pool', ''),
                rune_added=int(j.get('runeAdded', 0)),
                rune_withdrawn=int(j.get('runeWithdrawn', 0)),
                run_address=j.get('runeAddress', '')
            ))
        return results

    def parse_pool_membership(self, response) -> List[str]:
        pools = response.get('pools', [])
        return [p['pool'] for p in pools if 'pool' in p]

    def parse_last_block(self, response) -> Dict[str, LastBlock]:
        last_blocks = []
        for j in response:
            last_blocks.append(LastBlock(
                chain=j.get('chain', ''),
                last_observed_in=int(j.get('last_observed_in', 0)),
                last_signed_out=int(j.get('last_signed_out', 0)),
                thorchain=int(j.get('thorchain', 0))
            ))
        return {b.chain: b for b in last_blocks}

    def parse_pool_info(self, response) -> PoolInfoMap:
        pm = {}
        for j in response:
            asset = j['asset']
            pm[asset] = PoolInfo(
                asset=asset,
                balance_asset=int(j['assetDepth']),
                balance_rune=int(j['runeDepth']),
                pool_units=int(j['units']),
                status=str(j['status']).lower()
            )
        return pm


def get_parser_by_network_id(network_id) -> MidgardParserBase:
    if network_id in (NetworkIdents.TESTNET_MULTICHAIN, NetworkIdents.CHAOSNET_MULTICHAIN):
        return MidgardParserV2(network_id)
    elif network_id == NetworkIdents.CHAOSNET_BEP2CHAIN:
        return MidgardParserV1(network_id)
    else:
        raise KeyError('unsupported network ID!')
