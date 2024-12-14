from contextlib import suppress
from functools import lru_cache
from typing import Optional

from binance import Client
from binance.exceptions import BinanceAPIException

from lib.constants import thor_to_float
from lib.date_utils import MINUTE
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.money import pretty_dollar
from lib.utils import WithLogger, get_ttl_hash
from models.asset import Asset
from models.tx import ThorTx


def order_book_evaluate(action: str, order_book: dict, amount: float) -> Optional[float]:
    """
    bids ----> <----- asks
    buy ==> collect asks
    sell ==> collect bids
    order_book = [ ( price, amount ) ]
    :return: asset_out float
    """
    if not order_book:
        return

    buy = action == 'buy'
    book_side = order_book['asks'] if buy else order_book['bids']

    amount_left = amount
    out_asset = 0.0
    for p, a in book_side:
        p, a = float(p), float(a)
        total = p * a

        if buy:
            if amount_left <= total:
                out_asset += amount_left / p
                return out_asset
            else:
                out_asset += a
                amount_left -= total
        else:  # sell
            if amount_left <= a:
                out_asset += amount_left * p
                return out_asset
            else:
                out_asset += total
                amount_left -= a
    # Not enough liquidity to fulfill the order => None


class StreamingSwapVsCexProfitCalculator(WithLogger, WithDelegates, INotified):
    BINANCE_CACHE_TIME = 5 * MINUTE

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.binance = Client()
        self.logger.info(f'ProfitVsCEX is {"enabled" if self.is_enabled else "disabled"}')

    @property
    def is_enabled(self):
        return self.deps.cfg.get_pure('tx.estimated_savings_vs_cex_enabled', False)

    @classmethod
    def url_cex(cls, from_asset: Asset, to_asset: Asset, amount: float):
        return (
            f"https://api.criptointercambio.com/amount/exchange/full?"
            f"from={from_asset.name}&"
            f"to={to_asset.name}&"
            f"amount={amount}"
        )

    @classmethod
    def make_binance_symbol(cls, from_asset: str, to_asset: str):
        return f'{from_asset.upper()}{to_asset.upper()}'

    @lru_cache(maxsize=1024)
    def sync_binance_get_order_book(self, asset: str, quote_asset: str, ttl_hash=None):
        self.logger.info(f'Fetching Binance order book for {asset}/{quote_asset} ({ttl_hash} =)')
        with suppress(BinanceAPIException):
            return self.binance.get_order_book(symbol=self.make_binance_symbol(asset, quote_asset), limit=1000)

    async def binance_get_order_book(self, asset: str, quote_asset):
        return await self.deps.loop.run_in_executor(None, self.sync_binance_get_order_book,
                                                    asset, quote_asset,
                                                    get_ttl_hash(self.BINANCE_CACHE_TIME))

    async def binance_get_order_book_cached(self, asset: str, quote_asset='USDT'):
        return await self.binance_get_order_book(asset, quote_asset)

    async def binance_query(self, from_asset_obj: Asset, to_asset_obj: Asset, amount: float):
        from_asset = from_asset_obj.name
        to_asset = to_asset_obj.name

        if from_asset in ('USDT', 'BUSD'):
            book = await self.binance_get_order_book_cached(to_asset, quote_asset=from_asset)
            return order_book_evaluate('buy', book, amount)
        elif to_asset in ('USDT', 'BUSD'):
            book = await self.binance_get_order_book_cached(from_asset, quote_asset=to_asset)
            return order_book_evaluate('sell', book, amount)
        else:
            async def try_quote(quote):
                book1 = await self.binance_get_order_book_cached(from_asset, quote_asset=quote)
                book2 = await self.binance_get_order_book_cached(to_asset, quote_asset=quote)
                asset1 = order_book_evaluate('sell', book1, amount)
                if asset1 is not None:
                    return order_book_evaluate('buy', book2, asset1)

            return await try_quote('USDT') or await try_quote('BUSD')

    TC_PROFIT_VS_CEX_TOO_MUCH_RATIO = 0.4

    async def get_cex_data_v2(self, tx: ThorTx):
        """
        Get CEX output at the moment!
        @param tx:
        @return:
        """
        # We simply do not calculate profit it the swap was not fully fulfilled (it has refund part)
        if tx.refund_coin:
            return

        asset_in = tx.first_input_tx.first_asset
        asset_out = tx.first_output_tx.first_asset
        if not asset_in or not asset_out:
            return

        asset_in = Asset.from_string(asset_in)
        asset_out = Asset.from_string(asset_out)

        if asset_in.native_pool_name == asset_out.native_pool_name:
            # Synth wrap/unwrap. Ignore
            return

        amount = thor_to_float(tx.first_input_tx.first_amount)

        asset_out_amount = await self.binance_query(asset_in, asset_out, amount)
        if not asset_out_amount:
            self.logger.warning(f'Failed to estimate swap out through Binance!')
            return

        tx.meta_swap.cex_out_amount = asset_out_amount

        self._finalize_tx(tx)

    async def get_cex_data_v1(self, tx: ThorTx):
        """
        Get CEX output at the moment!
        @param tx:
        @return:
        """
        asset_in = tx.first_input_tx.first_asset
        asset_out = tx.first_output_tx.first_asset
        if not asset_in or not asset_out:
            return

        url = self.url_cex(asset_in, asset_out, thor_to_float(tx.first_input_tx.first_amount))
        async with self.deps.session.get(url) as resp:
            data = await resp.json()
            data = data['fullExchangeAmount']

            tx.meta_swap.cex_out_amount = float(data['result'])

            self._finalize_tx(tx)

    def _finalize_tx(self, tx: ThorTx):
        savings_usd = tx.get_profit_vs_cex_in_usd(self.deps.price_holder)
        volume_usd = tx.get_usd_volume(self.deps.price_holder.usd_per_rune)

        if savings_usd is None:
            return

        if abs(savings_usd) > volume_usd * self.TC_PROFIT_VS_CEX_TOO_MUCH_RATIO:
            self.logger.warning(f'Tx {tx.tx_hash} has weird profit vs Cex {pretty_dollar(savings_usd)}; '
                                f'{tx.meta_swap.cex_out_amount=}')
            savings_usd = 0.0

        tx.meta_swap.estimated_savings_vs_cex_usd = savings_usd

        self.logger.info(f'Tx {tx.tx_hash} profit vs CEX: {pretty_dollar(savings_usd)}')

    async def _process_transactions(self, txs):
        try:
            for tx in txs:
                tx: ThorTx
                if tx.is_streaming:
                    await self.get_cex_data_v2(tx)
        except Exception as e:
            self.logger.error(f'Error! {e!r}. Skipping this TX')

            with suppress(Exception):
                self.deps.emergency.report('ProfitVsCEX',
                                           txs=', '.join([tx.tx_hash for tx in data]),
                                           error=repr(e))

    async def on_data(self, sender, data):
        if self.is_enabled:
            await self._process_transactions(data)
        await self.pass_data_to_listeners(data)
