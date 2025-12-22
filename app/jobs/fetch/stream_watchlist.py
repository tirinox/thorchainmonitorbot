import json

from jobs.fetch.base import BaseFetcher
from lib.constants import thor_to_float
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from lib.utils import safe_get
from models.memo import THORMemo
from models.price import PriceHolder
from models.s_swap import StreamingSwap, EventChangedStreamingSwapList, AlertSwapStart


class StreamingSwapWatchListFetcher(BaseFetcher):
    """
    Responsible for fetching the list of ongoing streaming swaps from THORChain (/thorchain/swaps/streaming)
    Keeps track of the list of TXIDs in the DB and generates events when new streaming swaps are detected or existing ones are completed.
    """

    def __init__(self, deps: DepContainer):
        sleep_period = deps.cfg.as_interval("tx.swap.streaming_watchlist.period", default="10s")
        super().__init__(deps, sleep_period)

    async def fetch(self) -> EventChangedStreamingSwapList:
        raw_s_swaps = await self.load_current_state_raw()
        if not isinstance(raw_s_swaps, list):
            raise ValueError(f'Invalid response from /thorchain/swaps/streaming: {raw_s_swaps}')

        parsed_s_swaps = [StreamingSwap.model_validate(ss) for ss in raw_s_swaps]

        previous_s_swaps = await self.load_list_from_db()

        changes = self.compare_lists(previous_s_swaps, parsed_s_swaps)

        if changes:
            await self.save_raw_list_to_db(raw_s_swaps)

        return changes

    DB_KEY = 'tx:streaming_watchlist:prev_list'

    async def load_current_state_raw(self):
        return await self.deps.thor_connector.query_raw('/thorchain/swaps/streaming')

    async def load_list_from_db(self):
        r = await self.deps.db.get_redis()
        data = await r.get(self.DB_KEY)
        data_list = json.loads(data) if data else []
        txs = [StreamingSwap.model_validate(s) for s in data_list]
        return txs

    async def save_raw_list_to_db(self, s_swaps: list[dict]):
        r = await self.deps.db.get_redis()
        await r.set(self.DB_KEY, json.dumps(s_swaps))

    @staticmethod
    def compare_lists(old: list[StreamingSwap], new: list[StreamingSwap]) -> EventChangedStreamingSwapList:
        old_map = {s.tx_id: s for s in old}
        new_map = {s.tx_id: s for s in new}

        added = [s for tx_id, s in new_map.items() if tx_id not in old_map]
        removed = [s for tx_id, s in old_map.items() if tx_id not in new_map]

        return EventChangedStreamingSwapList(
            new_swaps=added,
            completed_swaps=removed,
        )


class StreamingSwapStatusChecker(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    DB_KEY_TRACKED_SWAPS = 'tx:streaming_watchlist:tracked_swaps'

    async def on_data(self, sender, data: EventChangedStreamingSwapList):
        # handles data.completed_swaps
        completed_tx_ids = [s.tx_id for s in data.completed_swaps]
        await self._add_tracked_tx_ids(completed_tx_ids)

        await self._check_all_tracked_swaps()

    async def _check_all_tracked_swaps(self, max_tx_to_check: int = 50):
        tracked_tx_ids = await self.get_tracked_tx_ids()
        if len(tracked_tx_ids) > max_tx_to_check:
            self.logger.warning(
                f'Too many tracked streaming swap txs ({len(tracked_tx_ids)}), checking only first {max_tx_to_check}.')
            tracked_tx_ids = list(tracked_tx_ids)[:max_tx_to_check]

        for tx_id in tracked_tx_ids:
            details = await self.deps.thor_connector.query_tx_details(tx_id)
            status = safe_get(details, 'tx', 'tx', 'status')
            if status == 'done':
                self.logger.info(f'Streaming swap tx {tx_id} has been completed on-chain.')
                await self._remove_tracked_tx_ids([tx_id])

                # todo: notify subscribers about completed tracked swap
                await self.pass_data_to_listeners((tx_id, details))
            elif status is not None:
                self.deps.emergency.report("SwapWatchlist", "Unknown streaming swap status",
                                           status=status,
                                           tx_id=tx_id)

    async def get_tracked_tx_ids(self) -> set[str]:
        r = await self.deps.db.get_redis()
        data = await r.smembers(self.DB_KEY_TRACKED_SWAPS)
        return data

    async def _add_tracked_tx_ids(self, tx_ids: list[str]):
        if tx_ids:
            r = await self.deps.db.get_redis()
            await r.sadd(self.DB_KEY_TRACKED_SWAPS, *tx_ids)

    async def _remove_tracked_tx_ids(self, tx_ids: list[str]):
        if tx_ids:
            r = await self.deps.db.get_redis()
            await r.srem(self.DB_KEY_TRACKED_SWAPS, *tx_ids)


class StreamingSwapStartDetector(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    async def on_data(self, sender, data: EventChangedStreamingSwapList):
        # handles data.new_swap,
        # passed "AlertSwapStart" further
        if not data.new_swaps:
            return

        self.logger.info(f'Detected {len(data.new_swaps)} new streaming swaps.')

        ph: PriceHolder = await self.deps.pool_cache.get()

        for s in data.new_swaps:
            # insolated handling of each swap
            try:
                await self._handle_swap_start(s, ph)
            except Exception as e:
                self.logger.exception(f'Error handling streaming swap start {s.tx_id}: {e!r}')
                self.deps.emergency.report('StreamingSwapStartDetector', 'Error handling streaming swap start',
                                           tx_id=s.tx_id)

    async def _handle_swap_start(self, s: StreamingSwap, ph: PriceHolder):
        details = await self.deps.thor_connector.query_tx_details(s.tx_id)

        tx_contents = safe_get(details, 'tx', 'tx')
        memo = THORMemo.parse_memo(raw_tx_memo := tx_contents.get('memo', ''), no_raise=True)
        from_address = tx_contents.get('from_address', '')

        block_height = details.get('consensus_height', s.last_height)
        coin = safe_get(details, 'tx', 'tx', 'coins', 0)
        asset, amount = coin['asset'], thor_to_float(coin['amount']) if coin else (None, 0.0)
        price_source_asset = ph.get_asset_price_in_usd(asset)
        volume_usd = amount * price_source_asset

        await self.pass_data_to_listeners(AlertSwapStart(
            tx_id=s.tx_id,
            from_address=from_address,
            destination_address=memo.dest_address,
            in_amount=amount,
            in_asset=s.source_asset,
            out_asset=s.target_asset,
            volume_usd=volume_usd,
            block_height=block_height,
            memo=memo,
            memo_str=raw_tx_memo,
            interval=s.interval,
            quantity=s.quantity,
        ))
