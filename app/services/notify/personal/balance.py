import asyncio
from collections import defaultdict
from typing import List

from services.lib.db import DB
from services.lib.delegates import INotified
from services.lib.depcont import DepContainer
from services.lib.midgard.name_service import NameMap
from services.lib.money import Asset, ABSURDLY_LARGE_NUMBER
from services.lib.settings_manager import SettingsManager
from services.lib.texts import grouper
from services.lib.utils import class_logger, safe_get
from services.models.node_watchers import UserWatchlist
from services.models.transfer import RuneTransfer
from services.notify.channel import ChannelDescriptor, BoardMessage
from services.notify.personal.helpers import GeneralSettings, Props


class WalletWatchlist(UserWatchlist):
    def __init__(self, db: DB):
        super().__init__(db, 'Wallet')


class PersonalBalanceNotifier(INotified):
    MAX_TRANSFER_PER_MESSAGE = 3

    def __init__(self, d: DepContainer):
        self.deps = d
        self._watcher = WalletWatchlist(d.db)
        self.logger = class_logger(self)

    async def on_data(self, sender, transfers: List[RuneTransfer]):
        self._fill_asset_price(transfers)

        addresses = set()
        for transfer in transfers:
            addresses.update((transfer.to_addr, transfer.from_addr))

        if not addresses:
            return

        self.logger.debug(f'Casting transfer events ({len(addresses)} items)')

        address_to_user = await self._watcher.all_users_for_many_nodes(addresses)
        all_affected_users = self._watcher.all_affected_users(address_to_user)
        user_to_address = self._watcher.reverse(address_to_user)

        # for addr, users in address_to_user.items():
        #     print(f"{addr} => {users}!")

        if not all_affected_users:
            return

        user_events = defaultdict(list)
        for transfer in transfers:
            users_for_event = set(address_to_user.get(transfer.from_addr)) | set(address_to_user.get(transfer.to_addr))

            for user in users_for_event:
                user_events[user].append(transfer)

        settings_dic = await self.deps.settings_manager.get_settings_multi(user_events.keys())

        # load THORNames
        name_map = await self._load_thornames_from_events(user_events)

        for user, event_list in user_events.items():
            settings = settings_dic.get(user, {})

            if bool(settings.get(GeneralSettings.INACTIVE, False)):
                continue  # paused

            # filter events according to the user's setting
            filtered_event_list = await self._filter_events(event_list, user, settings)

            # split to several messages
            groups = list(grouper(self.MAX_TRANSFER_PER_MESSAGE, filtered_event_list))

            if groups:
                self.logger.info(f'Sending personal Rune transfer notifications to user: {user}: '
                                 f'{len(event_list)} events grouped to {len(groups)} groups...')

                my_addresses = user_to_address.get(user, [])

                for group in groups:
                    await self._send_message_to_group(group, settings, user, my_addresses, name_map)

    async def _send_message_to_group(self, group, settings, user, my_addresses, name_map):
        loc = await self.deps.loc_man.get_from_db(user, self.deps.db)
        platform = SettingsManager.get_platform(settings)

        messages = [loc.notification_text_rune_transfer(transfer, my_addresses, name_map) for transfer in group]
        text = '\n\n'.join(m for m in messages if m)
        text = text.strip()
        if text:
            task = self.deps.broadcaster.safe_send_message_rate(
                ChannelDescriptor(platform, user),
                BoardMessage(text),
                disable_web_page_preview=True
            )
            asyncio.create_task(task)

    async def _load_thornames_from_events(self, user_events: dict) -> NameMap:
        all_addresses = set()
        for user_event_list in user_events.values():
            for event in user_event_list:
                event: RuneTransfer
                all_addresses.update((event.from_addr, event.to_addr))
        return await self.deps.name_service.safely_load_thornames_from_address_set(all_addresses)

    def _fill_asset_price(self, transfers):
        usd_per_rune = self.deps.price_holder.usd_per_rune
        for tr in transfers:
            tr: RuneTransfer
            if tr.is_rune:
                tr.usd_per_asset = usd_per_rune
            else:
                pool_name = Asset.from_string(tr.asset).native_pool_name
                tr.usd_per_asset = self.deps.price_holder.usd_per_asset(pool_name)

    @staticmethod
    def _get_min_rune_threshold(balance_settings: dict, address):
        if address in balance_settings:
            add_obj = balance_settings.get(address, {})
            if add_obj.get(Props.PROP_TRACK_BALANCE, False):
                return float(balance_settings.get(address, {}).get(Props.PROP_MIN_LIMIT, 0.0))
        # else:
        return ABSURDLY_LARGE_NUMBER

    async def _filter_events(self, event_list: List[RuneTransfer], user_id, settings: dict) -> List[RuneTransfer]:
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
            # else:
            #     print(f'Filtered transfer: {transfer} too low')

        return results


class SettingsProcessorBalanceTracker(INotified):
    def __init__(self, mapping: WalletWatchlist):
        self.mapping = mapping

    async def on_data(self, sender: SettingsManager, data):
        #        channel_id, settings = data
        pass
