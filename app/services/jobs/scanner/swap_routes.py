from collections import defaultdict
from datetime import datetime, timedelta
from typing import List

from services.lib.db import DB
from services.lib.delegates import INotified
from services.lib.logs import WithLogger
from services.lib.money import pretty_dollar
from services.models.key_stats_model import SwapRouteEntry
from services.models.tx import ThorTx

ROUTE_SEP = '=='


class SwapRouteRecorder(WithLogger, INotified):
    def __init__(self, db: DB, key_prefix="tx"):
        super().__init__()
        self.redis = db.redis
        self.key_prefix = key_prefix
        self.days_to_keep = 60
        self.clear_every_ticks = 10
        self._clear_counter = 0

    @staticmethod
    def _date_format(date):
        return date.strftime('%d.%m.%Y')

    def _prefixed_key(self, route, date):
        return f"{self.key_prefix}:route:{route}:{self._date_format(date)}"

    async def store_swap_event(self, from_asset, to_asset, volume, dt: datetime):
        if volume <= 0:
            return

        route = f"{from_asset}{ROUTE_SEP}{to_asset}"
        key = self._prefixed_key(route, dt)
        await self.redis.hincrbyfloat(key, "volume", volume)
        self.logger.debug(f"Stored swap event: {route} {pretty_dollar(volume)} at {dt}")

    async def get_top_swap_routes_by_volume(self, days=7, top_n=3) -> List[SwapRouteEntry]:
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        date_range = [start_time + timedelta(days=i) for i in range(days + 1)]

        route_volume = defaultdict(float)

        key_start_pos = len(self.key_prefix) + 1

        for date in date_range:
            keys = await self.redis.keys(self._prefixed_key('*', date))

            for key in keys:
                route = key[key_start_pos:].split(':')[1]
                volume = float(await self.redis.hget(key, "volume") or 0)

                from_asset, to_asset = route.split(ROUTE_SEP)
                route_volume[(from_asset, to_asset)] += volume

        # Get the top N routes by volume
        top_routes = sorted(route_volume.items(), key=lambda item: item[1], reverse=True)[:top_n]

        # convert to SwapRouteEntry
        top_routes = [
            SwapRouteEntry(from_asset=from_asset, to_asset=to_asset, volume_cacao=volume)
            for (from_asset, to_asset), volume in top_routes
        ]

        return top_routes

    async def clear_old_events(self, days, look_back=90):
        cutoff_time = datetime.now() - timedelta(days=days)
        fail_count = 0
        total_deleted = 0
        while True:
            keys = await self.redis.keys(self._prefixed_key('*', cutoff_time))
            if keys:
                await self.redis.delete(*keys)
                total_deleted += len(keys)
            else:
                fail_count += 1
                if fail_count > look_back:
                    break

            cutoff_time -= timedelta(days=1)

        self.logger.info(f"Deleted {total_deleted} old swap events older than {days} days")

    async def _clear_routes_if_needed(self):
        if self.days_to_keep > 0:
            self._clear_counter += 1
            if self._clear_counter >= self.clear_every_ticks:
                self._clear_counter = 0
                await self.clear_old_events(self.days_to_keep)

    @property
    def key_counted_routes(self):
        return f"{self.key_prefix}:route:counted_routes"

    async def is_registered(self, tx_id):
        return await self.redis.sismember(self.key_counted_routes, tx_id)

    async def register(self, tx_id):
        await self.redis.sadd(self.key_counted_routes, tx_id)

    async def clear_registered(self):
        await self.redis.delete(self.key_counted_routes)

    async def on_data(self, sender, data: List[ThorTx]):
        for tx in data:
            if not tx.meta_swap:
                continue  # skip non-swap tx

            if tx.full_rune <= 0:
                self.logger.warning(f"Skip tx {tx.tx_hash} with zero RUNE amount")
                continue

            if await self.is_registered(tx.tx_hash):
                continue

            await self.store_swap_event(
                tx.first_input_tx.first_asset,
                tx.first_output_tx.first_asset,
                tx.full_rune,
                datetime.utcfromtimestamp(tx.date_timestamp)
            )

            await self.register(tx.tx_hash)

        # Sometimes we need to clear old dates
        await self._clear_routes_if_needed()
