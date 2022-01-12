import json
from typing import Tuple

from aiothornode.types import ThorConstants, ThorMimir

from localization import BaseLocalization
from services.jobs.fetch.base import INotified
from services.jobs.fetch.const_mimir import ConstMimirFetcher
from services.lib.date_utils import now_ts
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.mimir import MimirChange


class MimirChangedNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)

    @staticmethod
    def mimir_last_modification_key(name):
        return f'MimirLastChangeTS:{name}'

    async def last_mimir_change_date(self, name: str) -> float:
        if not name:
            return 0
        try:
            data = await self.deps.db.redis.get(self.mimir_last_modification_key(name))
            return float(data)
        except Exception:
            return 0

    async def _save_mimir_change_date(self, change: MimirChange):
        try:
            self.deps.mimir_const_holder.register_change_ts(change.name, change.timestamp)
            await self.deps.db.redis.set(self.mimir_last_modification_key(change.name), change.timestamp)
        except Exception as e:
            self.logger.error(f'Failed to save last Mimir change: {e}')

    async def _ensure_all_last_changes_in_holder(self, mimir: ThorMimir):
        if not self.deps.mimir_const_holder.last_changes:
            for name in mimir.constants.keys():
                ts = await self.last_mimir_change_date(name)
                self.deps.mimir_const_holder.register_change_ts(name, ts)

    async def on_data(self, sender: ConstMimirFetcher, data: Tuple[ThorConstants, ThorMimir]):
        _, fresh_mimir = data

        if not fresh_mimir or not fresh_mimir.constants:
            return

        await self._ensure_all_last_changes_in_holder(fresh_mimir)

        old_mimir = await self._get_saved_mimir_state()
        if not old_mimir:
            self.logger.warning('Mimir has not been saved yet. Waiting for the next tick...')
            await self._save_mimir_state(fresh_mimir)
            return

        fresh_const_names = set(fresh_mimir.constants.keys())
        old_const_names = set(old_mimir.constants.keys())
        all_const_names = fresh_const_names | old_const_names

        changes = []

        holder = self.deps.mimir_const_holder

        timestamp = now_ts()

        for name in all_const_names:
            change_kind = None
            old_value, new_value = None, None

            if name in fresh_const_names and name in old_const_names:
                old_value = old_mimir[name]
                new_value = fresh_mimir[name]
                if old_value != new_value:
                    change_kind = MimirChange.VALUE_CHANGE
            elif name in fresh_const_names and name not in old_const_names:
                new_value = fresh_mimir[name]
                old_value = holder.get_hardcoded_const(name)
                change_kind = MimirChange.ADDED_MIMIR
            elif name not in fresh_const_names and name in old_const_names:
                old_value = old_mimir[name]
                new_value = holder.get_hardcoded_const(name)
                change_kind = MimirChange.REMOVED_MIMIR

            if change_kind is not None:
                entry = self.deps.mimir_const_holder.get_entry(name)
                change = MimirChange(change_kind, name, old_value, new_value, entry, timestamp)
                changes.append(change)
                await self._save_mimir_change_date(change)

        if changes:
            await self.deps.broadcaster.notify_preconfigured_channels(
                BaseLocalization.notification_text_mimir_changed,
                changes,
                self.deps.mimir_const_holder,
            )

        if fresh_mimir and fresh_mimir.constants:
            await self._save_mimir_state(fresh_mimir)

    DB_KEY_MIMIR_LAST_STATE = 'Mimir:LastState'

    async def _get_saved_mimir_state(self):
        db = await self.deps.db.get_redis()
        raw_data = await db.get(self.DB_KEY_MIMIR_LAST_STATE)
        try:
            j = json.loads(raw_data)
            return ThorMimir.from_json(j)
        except (TypeError, ValueError):
            return None

    async def _save_mimir_state(self, c: ThorMimir):
        data = json.dumps(c.constants)
        db = await self.deps.db.get_redis()
        await db.set(self.DB_KEY_MIMIR_LAST_STATE, data)
