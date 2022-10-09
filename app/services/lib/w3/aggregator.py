from typing import Optional, List, Tuple

from web3.exceptions import TransactionNotFound

from services.lib.constants import Chains
from services.lib.delegates import WithDelegates, INotified
from services.lib.depcont import DepContainer
from services.lib.money import Asset
from services.lib.utils import WithLogger
from services.lib.w3.aggr_contract import AggregatorContract
from services.lib.w3.erc20_contract import ERC20Contract
from services.lib.w3.router_contract import TCRouterContract
from services.lib.w3.token_list import StaticTokenList, TokenListCached
from services.lib.w3.token_record import TokenRecord, AmountToken, SwapInOut
from services.lib.w3.web3_helper import Web3HelperCached
from services.models.tx import ThorTxExtended, ThorSubTx, ThorTxType


class AggregatorSingleChain:
    def __init__(self, deps: DepContainer, chain: str):
        self.deps = deps

        self.chain = chain
        self.l1_asset = Chains.l1_asset(chain)

        chain_id = Chains.web3_chain_id(chain)
        assert chain_id > 0
        static_list = StaticTokenList(StaticTokenList.DEFAULT_LISTS[chain], chain_id)
        self.w3 = Web3HelperCached(chain, deps.cfg, deps.db)
        self.token_list = TokenListCached(self.deps.db, self.w3, static_list)
        self.router = TCRouterContract(self.w3)
        self.aggregator = AggregatorContract(self.w3)

    @staticmethod
    def make_pair(amount, token_info: TokenRecord):
        return AmountToken(
            amount / 10 ** token_info.decimals,
            token_info,
        )

    async def decode_swap_out(self, tx_hash) -> Optional[AmountToken]:
        tx = await self.w3.get_transaction(tx_hash)

        swap_out_call = self.router.decode_input(tx['input'])
        if not swap_out_call:
            raise TransactionNotFound('this is not swap out')

        token = ERC20Contract(self.w3, swap_out_call.target_token, self.token_list.chain_id)

        receipt_data = await self.w3.get_transaction_receipt(tx_hash)
        transfers = token.get_transfer_events_from_receipt(receipt_data, filter_by_receiver=swap_out_call.to_address)
        final_transfer = transfers[0]
        amount = final_transfer['args']['value']

        token_info = await self.token_list.resolve_token(swap_out_call.target_token)
        return self.make_pair(amount, token_info)

    async def decode_swap_in(self, tx_hash) -> Optional[AmountToken]:
        tx = await self.w3.get_transaction(tx_hash)
        swap_in_call = self.aggregator.decode_input(tx['input'])
        if not swap_in_call:
            raise TransactionNotFound('this is not swap in')

        token_info = await self.token_list.resolve_token(swap_in_call.from_token)
        return self.make_pair(swap_in_call.amount, token_info)


class AggregatorDataExtractor(WithLogger, INotified, WithDelegates):
    DEFAULT_CHAINS = (Chains.ETH, Chains.AVAX)

    def __init__(self, deps: DepContainer, suitable_chains=DEFAULT_CHAINS):
        super().__init__()
        self.deps = deps
        self.asset_to_aggr = {
            Chains.l1_asset(chain): AggregatorSingleChain(deps, chain) for chain in suitable_chains
        }

    @staticmethod
    def chain_from_l1_asset(asset: str):
        return Asset.from_string(asset).chain

    def get_suitable_sub_tx_hash(self, tx: ThorSubTx) -> Tuple[Optional[AggregatorSingleChain], str]:
        for c in tx.coins:
            aggr = self.asset_to_aggr.get(c.asset)
            if aggr:
                return aggr, tx.tx_id
        return None, ''

    async def _try_detect_aggregator(self, tx: ThorSubTx, is_in):
        tx_hash, chain = '??', '??'
        tag = 'In' if is_in else 'Out'
        try:
            aggr, tx_hash = self.get_suitable_sub_tx_hash(tx)
            if not aggr:
                return
            if not tx_hash:
                self.logger.warning('No TX hash!')
                return

            chain = aggr.chain
            if is_in:
                return await aggr.decode_swap_in(tx_hash)
            else:
                return await aggr.decode_swap_out(tx_hash)
        except TransactionNotFound:
            self.logger.info(f'{tx_hash} ({chain}) is not Swap {tag}.')
        except (ValueError, AttributeError, TypeError, LookupError):
            self.logger.exception(f'Error decoding Swap {tag} @ {tx_hash} ({chain})')

    async def on_data(self, sender, txs: List[ThorTxExtended]):
        for tx in txs:
            if tx.type == ThorTxType.TYPE_SWAP:
                in_amount = await self._try_detect_aggregator(tx.first_input_tx, is_in=True)
                out_amount = await self._try_detect_aggregator(tx.first_output_tx, is_in=False)
                if in_amount or out_amount:
                    self.logger.info(f'DEX aggregator detected: IN({in_amount}), OUT({out_amount})')
                tx.dex_info = SwapInOut(in_amount, out_amount)

        await self.pass_data_to_listeners(txs, sender)  # pass through

    def get_by_chain(self, chain: str) -> Optional[AggregatorSingleChain]:
        return self.asset_to_aggr.get(Chains.l1_asset(chain))
