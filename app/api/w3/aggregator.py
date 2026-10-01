import asyncio
import re
from typing import Optional, List, Tuple

from web3.exceptions import TransactionNotFound

from lib.constants import Chains, thor_to_float
from lib.delegates import WithDelegates, INotified
from lib.depcont import DepContainer
from lib.logs import WithLogger
from lib.texts import shorten_text
from models.asset import Asset
from models.memo import ActionType, THORMemo
from models.tx import ThorAction, ThorSubTx
from .aggr_contract import AggregatorContract
from .erc20_contract import ERC20Contract
from .resolver import AggregatorResolver, DEFAULT_AGGREGATOR_RESOLVER_PATH
from .router_contract import TCRouterContract
from .token_list import StaticTokenList, TokenListCached
from .token_record import TokenRecord, AmountToken, SwapInOut, DEX_SOURCE_MEMO, DEX_SOURCE_CHAIN
from .web3_helper import Web3HelperCached

EVM_TX_HASH_RE = re.compile(r'^(0x)?[0-9a-fA-F]{64}$')


def is_evm_tx_hash(tx_hash: str) -> bool:
    return bool(tx_hash) and bool(EVM_TX_HASH_RE.match(str(tx_hash)))


class AggregatorSingleChain:
    def __init__(self, deps: DepContainer, chain: str):
        self.deps = deps

        self.chain = chain
        self.l1_asset = str(Asset.gas_asset_from_chain(chain))

        chain_id = Chains.web3_chain_id(chain)
        assert chain_id > 0
        static_list = StaticTokenList(StaticTokenList.DEFAULT_LISTS[chain], chain_id)
        self.w3 = Web3HelperCached(chain, deps.cfg, deps.db)
        self.token_list = TokenListCached(self.deps.db, self.w3, static_list)
        self.router = TCRouterContract(self.w3)
        self.aggregator = AggregatorContract(self.w3)
        self.aggregator_resolver = AggregatorResolver(DEFAULT_AGGREGATOR_RESOLVER_PATH)

    @staticmethod
    def amount_of(raw_amount, token_info: Optional[TokenRecord]) -> Optional[float]:
        if raw_amount is None:
            return None
        decimals = token_info.decimals if token_info else 18
        return raw_amount / 10 ** decimals

    def resolve_aggregator(self, query: str) -> Tuple[str, str]:
        """
        Find a known aggregator by its (possibly shortened) address.
        Returns (name, address). When it is unknown, the name is the shortened query.
        """
        query = str(query or '')
        if not query:
            return '', ''
        record = self.aggregator_resolver.search_aggregator_address(query, chain=self.chain)
        if isinstance(record, list):  # ambiguous: several aggregators match the shortened address
            record = record[0] if len(record) == 1 else None
        if record:
            return record.name, record.address
        return shorten_text(query, limit=20), query

    def search_aggregator(self, tc_aggregator) -> str:
        return self.resolve_aggregator(tc_aggregator)[0]

    async def _load_tx(self, tx_hash):
        tx = await self.w3.get_transaction(tx_hash)
        if not tx:  # web3 helper returns None when all retries failed
            raise TransactionNotFound(f'could not load tx {tx_hash}')
        return tx

    async def decode_swap_out(self, tx_hash) -> Optional[AmountToken]:
        """
        The outbound transaction: TC router "transferOutAndCall" -> aggregator -> final token -> recipient.
        Gives the actual amount received by the recipient.
        """
        tx = await self._load_tx(tx_hash)

        swap_out_call = self.router.decode_input(tx['input'])
        if not swap_out_call:
            raise TransactionNotFound('this is not swap out')

        token_info = await self.token_list.resolve_token(swap_out_call.target_token)

        amount = None
        receipt_data = await self.w3.get_transaction_receipt(tx_hash)
        if receipt_data:
            token = ERC20Contract(self.w3, swap_out_call.target_token, self.token_list.chain_id)
            transfers = token.get_transfer_events_from_receipt(receipt_data,
                                                               filter_by_receiver=swap_out_call.to_address)
            if transfers:
                amount = self.amount_of(transfers[-1]['args']['value'], token_info)

        aggr_name, aggr_address = self.resolve_aggregator(swap_out_call.tc_aggregator)
        return AmountToken(
            amount, token_info,
            aggr_name=aggr_name,
            aggr_address=aggr_address,
            token_address=swap_out_call.target_token or '',
            chain=self.chain,
            source=DEX_SOURCE_CHAIN,
            recipient=swap_out_call.to_address or '',
        )

    async def decode_swap_in(self, tx_hash) -> Optional[AmountToken]:
        """
        The inbound transaction: user -> aggregator "swapIn" -> TC router deposit.
        Gives the source token and its amount.
        """
        tx = await self._load_tx(tx_hash)

        tx_to = tx.get('to') or ''
        aggr_name, aggr_address = '', ''
        if tx_to:
            record = self.aggregator_resolver.search_aggregator_address(tx_to, chain=self.chain)
            if record and not isinstance(record, list):
                aggr_name, aggr_address = record.name, record.address

        swap_in_call = self.aggregator.decode_input(tx['input'])
        if not swap_in_call:
            if aggr_name:
                # The ABI did not match (another aggregator version), but the call went to a known aggregator
                return AmountToken(
                    None, None,
                    aggr_name=aggr_name, aggr_address=aggr_address,
                    chain=self.chain, source=DEX_SOURCE_CHAIN,
                )
            raise TransactionNotFound('this is not swap in')

        if not aggr_name and tx_to:
            aggr_name, aggr_address = shorten_text(tx_to, limit=20), tx_to

        token_info = await self.token_list.resolve_token(swap_in_call.from_token)
        return AmountToken(
            self.amount_of(swap_in_call.amount, token_info), token_info,
            aggr_name=aggr_name,
            aggr_address=aggr_address,
            token_address=swap_in_call.from_token or '',
            chain=self.chain,
            source=DEX_SOURCE_CHAIN,
        )

    async def describe_swap_out_from_memo(self, memo: THORMemo) -> Optional[AmountToken]:
        """
        The swap memo tells the aggregator and the final token for the outbound leg.
        This is available right away, even before the outbound is broadcast, but it does not tell the amount.
        """
        if not memo or not memo.uses_aggregator_out:
            return None

        aggr_name, aggr_address = self.resolve_aggregator(memo.dex_aggregator_address)
        token_info = None
        if memo.final_asset_address:
            token_info = await self.token_list.resolve_token(memo.final_asset_address)

        return AmountToken(
            None, token_info,
            aggr_name=aggr_name,
            aggr_address=aggr_address,
            token_address=memo.final_asset_address or '',
            chain=self.chain,
            source=DEX_SOURCE_MEMO,
        )


class AggregatorDataExtractor(WithLogger, INotified, WithDelegates):
    DEFAULT_CHAINS = (Chains.ETH, Chains.AVAX, Chains.BSC, Chains.BASE)

    # Only swaps at least this big get the outbound decoded on-chain (1-2 RPC calls each); the memo is enough for
    # the rest. Shares the key with the swap notifier so that every alerted DEX swap has the full picture.
    DEFAULT_ON_CHAIN_OUT_MIN_USD = 500.0
    DEFAULT_RPC_TIMEOUT = 30.0

    def __init__(self, deps: DepContainer, suitable_chains=DEFAULT_CHAINS):
        super().__init__()
        self.deps = deps
        self.asset_to_aggr = {}
        for chain in suitable_chains:
            if not self._chain_is_configured(chain):
                self.logger.warning(f'No "web3.{chain}.rpc" in the config, DEX aggregator detection is off for {chain}')
                continue
            self.asset_to_aggr[str(Asset.gas_asset_from_chain(chain))] = AggregatorSingleChain(deps, chain)

        cfg = deps.cfg
        self.on_chain_out_min_usd = self.DEFAULT_ON_CHAIN_OUT_MIN_USD
        self.rpc_timeout = self.DEFAULT_RPC_TIMEOUT
        if cfg is not None:
            self.on_chain_out_min_usd = cfg.as_float(
                'tx.swap.also_trigger_when.dex_aggregator_used.min_usd_total', self.DEFAULT_ON_CHAIN_OUT_MIN_USD)
            self.rpc_timeout = cfg.as_interval('web3.timeout', f'{self.DEFAULT_RPC_TIMEOUT:.0f}s')

    def _chain_is_configured(self, chain: str) -> bool:
        cfg = self.deps.cfg
        if cfg is None:
            return False
        try:
            return bool(cfg.get_pure(f'web3.{chain}.rpc'))
        except LookupError:
            return False

    @property
    def assets_to_trigger(self):
        return list(self.asset_to_aggr.keys())

    @staticmethod
    def chain_from_l1_asset(asset: str):
        return Asset.from_string(asset).chain

    def get_by_chain(self, chain: str) -> Optional[AggregatorSingleChain]:
        if not chain:
            return None
        return self.asset_to_aggr.get(str(Asset.gas_asset_from_chain(chain)))

    def get_by_asset(self, asset: str) -> Optional[AggregatorSingleChain]:
        """
        The aggregator of the chain whose gas asset this is. Accepts full names ("ETH.ETH")
        and memo abbreviations ("e").
        """
        if not asset:
            return None
        asset = Asset.SHORT_NAMES.get(str(asset).lower(), asset)
        return self.asset_to_aggr.get(str(asset).upper())

    def get_suitable_sub_tx_hash(self, tx: ThorSubTx) -> Tuple[Optional[AggregatorSingleChain], str]:
        if not tx:
            return None, ''
        for c in tx.coins:
            aggr = self.asset_to_aggr.get(c.asset)
            if aggr:
                return aggr, tx.tx_id
        return None, ''

    async def _with_timeout(self, coro):
        return await asyncio.wait_for(coro, timeout=self.rpc_timeout)

    # ---- Swap-in ----

    async def _detect_swap_in(self, tx: ThorAction) -> Optional[AmountToken]:
        sub_tx = tx.first_input_tx
        aggr, tx_hash = self.get_suitable_sub_tx_hash(sub_tx)
        if not aggr:
            return None
        if not is_evm_tx_hash(tx_hash):
            self.logger.warning(f'Swap in of {tx.tx_hash}: "{tx_hash}" is not an EVM tx hash ({aggr.chain})')
            return None
        try:
            return await self._with_timeout(aggr.decode_swap_in(tx_hash))
        except TransactionNotFound:
            self.logger.info(f'{tx_hash} ({aggr.chain}) is not Swap In.')
        except Exception:
            self.logger.exception(f'Error decoding Swap In @ {tx_hash} ({aggr.chain})')
        return None

    # ---- Swap-out ----

    @staticmethod
    def _safe_memo(tx: ThorAction) -> Optional[THORMemo]:
        try:
            return tx.memo
        except Exception:
            return None

    def _out_aggregator(self, tx: ThorAction, memo: Optional[THORMemo]) -> Optional[AggregatorSingleChain]:
        """The chain of the outbound leg: from the memo target asset first, then from the actual outbound."""
        if memo and memo.asset:
            aggr = self.get_by_asset(memo.asset)
            if aggr:
                return aggr
        for sub_tx in (tx.recipients_output, tx.first_output_tx):
            aggr, _ = self.get_suitable_sub_tx_hash(sub_tx)
            if aggr:
                return aggr
        return None

    async def _swap_out_from_memo(self, tx: ThorAction, memo: THORMemo,
                                  aggr: AggregatorSingleChain) -> Optional[AmountToken]:
        try:
            return await self._with_timeout(aggr.describe_swap_out_from_memo(memo))
        except Exception:
            self.logger.exception(f'Error describing Swap Out from memo of {tx.tx_hash} ({aggr.chain})')
            # keep what we know without touching the token list
            aggr_name, aggr_address = aggr.resolve_aggregator(memo.dex_aggregator_address)
            return AmountToken(
                None, None,
                aggr_name=aggr_name, aggr_address=aggr_address,
                token_address=memo.final_asset_address or '',
                chain=aggr.chain, source=DEX_SOURCE_MEMO,
            )

    def _out_sub_tx_for_chain_decode(self, tx: ThorAction, aggr: AggregatorSingleChain) -> Optional[ThorSubTx]:
        sub_tx = tx.recipients_output or tx.first_output_tx
        if not sub_tx or not is_evm_tx_hash(sub_tx.tx_id):
            return None
        if not any(c.asset == aggr.l1_asset for c in sub_tx.coins):
            return None
        # The block scanner may put the inbound hash into the outbound sub tx before the outbound is signed
        inbound_hashes = {str(t.tx_id).lower() for t in tx.in_tx if t.tx_id}
        if str(sub_tx.tx_id).lower() in inbound_hashes:
            return None
        return sub_tx

    async def _swap_out_from_chain(self, tx: ThorAction, aggr: AggregatorSingleChain) -> Optional[AmountToken]:
        sub_tx = self._out_sub_tx_for_chain_decode(tx, aggr)
        if not sub_tx:
            return None
        tx_hash = sub_tx.tx_id
        try:
            return await self._with_timeout(aggr.decode_swap_out(tx_hash))
        except TransactionNotFound:
            self.logger.info(f'{tx_hash} ({aggr.chain}) is not Swap Out.')
        except Exception:
            self.logger.exception(f'Error decoding Swap Out @ {tx_hash} ({aggr.chain})')
        return None

    async def _detect_swap_out(self, tx: ThorAction, usd_volume: Optional[float]) -> Optional[AmountToken]:
        memo = self._safe_memo(tx)
        aggr = self._out_aggregator(tx, memo)
        if not aggr:
            return None

        leg = None
        if memo:
            if not memo.uses_aggregator_out:
                return None  # the memo is explicit: no aggregator on the way out
            leg = await self._swap_out_from_memo(tx, memo, aggr)

        # The on-chain decode is worth it only for the big swaps (or when there is no memo to rely on)
        if memo is None or (usd_volume is not None and usd_volume >= self.on_chain_out_min_usd):
            chain_leg = await self._swap_out_from_chain(tx, aggr)
            if chain_leg:
                leg = leg.merge_on_chain(chain_leg) if leg else chain_leg

        return leg

    # ---- USD estimate for the threshold ----

    async def _get_price_holder(self):
        pool_cache = getattr(self.deps, 'pool_cache', None)
        if pool_cache is None:
            return None
        try:
            return await pool_cache.get()
        except Exception:
            self.logger.exception('Failed to get the pool cache for the DEX aggregator USD estimate')
            return None

    @staticmethod
    def estimate_usd_volume(tx: ThorAction, ph) -> Optional[float]:
        """
        The volume filler runs after this stage, so the full volume is usually not known yet.
        Estimate it from the input coins then.
        """
        if not ph or not ph.usd_per_rune:
            return None
        if tx.full_volume_in_rune > 0:
            return tx.full_volume_in_rune * ph.usd_per_rune
        total = 0.0
        for sub_tx in tx.in_tx:
            for coin in sub_tx.coins:
                usd = ph.convert_to_usd(thor_to_float(coin.amount), coin.asset)
                if usd:
                    total += usd
        return total if total > 0 else None

    # ---- Pipeline ----

    async def detect(self, tx: ThorAction, ph=None) -> SwapInOut:
        usd_volume = self.estimate_usd_volume(tx, ph)
        swap_in = await self._detect_swap_in(tx)
        swap_out = await self._detect_swap_out(tx, usd_volume)
        if swap_in or swap_out:
            self.logger.info(f'DEX aggregator detected for {tx.tx_hash}: IN({swap_in}), OUT({swap_out})')
        return SwapInOut(swap_in, swap_out)

    async def on_data(self, sender, txs: List[ThorAction]):
        if self.asset_to_aggr and txs:
            ph = await self._get_price_holder()
            for tx in txs:
                # One bad tx must not break the rest of the batch
                try:
                    if tx.is_of_type(ActionType.SWAP):
                        tx.dex_info = await self.detect(tx, ph)
                except Exception:
                    self.logger.exception(f'DEX aggregator detection failed for {getattr(tx, "tx_hash", tx)}')

        await self.pass_data_to_listeners(txs, sender)  # pass through
