import logging
from abc import abstractmethod, ABC, ABCMeta
from typing import NamedTuple, List

from aiothornode.types import TEST_NET_ENVIRONMENT_MULTI_1, CHAOS_NET_BNB_ENVIRONMENT

from services.lib.config import Config
from services.lib.constants import NetworkIdents
from services.models.tx import ThorTx, ThorTxType, ThorSubTx, ThorMetaRefund, ThorMetaWithdraw, ThorMetaSwap, \
    ThorMetaAddLiquidity

logger = logging.getLogger(__name__)


def get_midgard_url(cfg: Config, path: str):
    if cfg.network_id == NetworkIdents.TESTNET_MULTICHAIN:
        version = 'v2'
        base_url = TEST_NET_ENVIRONMENT_MULTI_1.midgard_url
    elif cfg.network_id == NetworkIdents.CHAOSNET_BEP2CHAIN:
        base_url = CHAOS_NET_BNB_ENVIRONMENT.midgard_url
        version = 'v1'
    elif cfg.network_id == NetworkIdents.CHAOSNET_MULTICHAIN:
        raise NotImplementedError
    else:
        raise NotImplementedError
    base_url = base_url.rstrip('/')
    path = path.lstrip('/')
    full_path = f"{base_url}/{version}/{path}"
    return full_path


class MidgardURLGenBase(ABC):
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')

    @abstractmethod
    def url_for_tx(self, offset=0, count=50) -> str:
        ...

    @abstractmethod
    def url_for_pool_depth_history(self, pool, from_ts, to_ts) -> str:
        ...


class MidgardURLGenV1(MidgardURLGenBase):
    def url_for_tx(self, offset=0, count=50) -> str:
        return f'{self.base_url}/v1/txs?offset={offset}&limit={count}'

    def url_for_pool_depth_history(self, pool, from_ts, to_ts) -> str:
        return f"{self.base_url}/v1/history/pools?pool={pool}&interval=day&from={from_ts}&to={to_ts}"


class MidgardURLGenV2(MidgardURLGenBase):
    def url_for_tx(self, offset=0, count=50) -> str:
        return f'{self.base_url}/v2/actions?offset={offset}&limit={count}'

    def url_for_pool_depth_history(self, pool, from_ts, to_ts) -> str:
        return f"{self.base_url}/v2/history/depths/{pool}?interval=day&from={from_ts}&to={to_ts}"


def get_url_gen_by_network_id(network_id) -> MidgardURLGenBase:
    if network_id == NetworkIdents.TESTNET_MULTICHAIN:
        return MidgardURLGenV2(TEST_NET_ENVIRONMENT_MULTI_1.midgard_url)
    elif network_id == NetworkIdents.CHAOSNET_BEP2CHAIN:
        return MidgardURLGenV1(CHAOS_NET_BNB_ENVIRONMENT.midgard_url)
    else:
        raise KeyError('unsupported network ID!')


class TxParseResult(NamedTuple):
    total_count: int = 0
    txs: List[ThorTx] = None
    tx_count_unfiltered: int = 0
    network_id: str = ''

    @property
    def tx_count(self):
        return len(self.txs)


class TxParserBase(metaclass=ABCMeta):
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


class TxParserV1(TxParserBase):
    """
    Midgard V1 + Single chain BEP Swap network
    """

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


class TxParserV2(TxParserBase):
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


def get_parser_by_network_id(network_id) -> TxParserBase:
    if network_id in (NetworkIdents.TESTNET_MULTICHAIN, NetworkIdents.CHAOSNET_MULTICHAIN):
        return TxParserV2(network_id)
    elif network_id == NetworkIdents.CHAOSNET_BEP2CHAIN:
        return TxParserV1(network_id)
    else:
        raise KeyError('unsupported network ID!')
