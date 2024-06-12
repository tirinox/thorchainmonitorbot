from typing import List

from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.lib.money import ABSURDLY_LARGE_NUMBER
from services.lib.utils import safe_get
from services.models.asset import Asset
from services.models.node_watchers import UserWatchlist
from services.models.transfer import RuneTransfer
from services.notify.personal.base import BasePersonalNotifier
from services.notify.personal.helpers import GeneralSettings, Props


class WalletWatchlist(UserWatchlist):
    def __init__(self, db: DB):
        super().__init__(db, 'Wallet')


class PersonalBalanceNotifier(BasePersonalNotifier):
    MAX_TRANSFER_PER_MESSAGE = 3

    def __init__(self, d: DepContainer):
        watcher = WalletWatchlist(d.db)
        super().__init__(d, watcher)

    async def on_data(self, sender, transfers: List[RuneTransfer]):
        self._fill_asset_price(transfers)

        # Collect all listed addresses
        addresses = set()
        for transfer in transfers:
            addresses.update((transfer.to_addr, transfer.from_addr))

        if not addresses:
            return

        # Group, filter and send
        await self.group_and_send_messages(addresses, transfers)

    def _fill_asset_price(self, transfers):
        usd_per_rune = self.deps.price_holder.usd_per_rune
        for tr in transfers:
            tr: RuneTransfer
            if tr.is_rune:
                tr.usd_per_asset = usd_per_rune
            else:
                pool_name = Asset.from_string(tr.asset).native_pool_name
                tr.usd_per_asset = self.deps.price_holder.usd_per_asset(pool_name) or 0.0

    @staticmethod
    def _get_min_rune_threshold(balance_settings: dict, address):
        if address in balance_settings:
            add_obj = balance_settings.get(address, {})
            if add_obj.get(Props.PROP_TRACK_BALANCE, False):
                return float(balance_settings.get(address, {}).get(Props.PROP_MIN_LIMIT, 0.0))
        # else:
        return ABSURDLY_LARGE_NUMBER

    async def filter_events(self, event_list: List[RuneTransfer], user_id, settings: dict) -> List[RuneTransfer]:
        balance_settings = safe_get(settings, GeneralSettings.BALANCE_TRACK, Props.KEY_ADDRESSES)
        if not isinstance(balance_settings, dict):
            # no preferences: return all!
            return event_list

        results = []

        usd_per_rune = self.deps.price_holder.usd_per_rune

        for transfer in event_list:
            min_threshold_rune = min(
                self._get_min_rune_threshold(balance_settings, transfer.to_addr),
                self._get_min_rune_threshold(balance_settings, transfer.from_addr)
            )

            if transfer.rune_amount(usd_per_rune) >= min_threshold_rune:
                results.append(transfer)

        return results

    def get_users_from_event(self, ev: RuneTransfer, address_to_user):
        return list(address_to_user.get(ev.from_addr)) + list(address_to_user.get(ev.to_addr))

    async def generate_message_text(self, loc, group, settings, user, user_watch_addy_list, name_map):
        return [loc.notification_text_rune_transfer(transfer, user_watch_addy_list, name_map) for transfer in group]
