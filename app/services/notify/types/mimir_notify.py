import json
import random
from typing import Tuple, Optional

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

    def _dbg_randomize_mimir(self, fresh_mimir: ThorMimir):
        # if random.uniform(0, 1) > 0.5:
        #     fresh_mimir.constants['mimir//LOKI_CONST'] = "555"
        # if random.uniform(0, 1) > 0.3:
        #     fresh_mimir.constants['mimir//LOKI_CONST'] = "777"
        # if random.uniform(0, 1) > 0.6:
        #     fresh_mimir.constants['mimir//NativeTransactionFee'] = 300000
        # if random.uniform(0, 1) > 0.3:
        #     try:
        #         del fresh_mimir.constants['mimir//NativeTransactionFee']
        #     except KeyError:
        #         pass
        del fresh_mimir.constants["mimir//HALTBNBTRADING"]
        fresh_mimir.constants["mimir//HALTETHTRADING"] = 1
        # del fresh_mimir.constants["mimir//EMISSIONCURVE"]
        # fresh_mimir.constants['mimir//NATIVETRANSACTIONFEE'] = 300000
        fresh_mimir.constants['mimir//MAXLIQUIDITYRUNE'] = 10000000000000 * random.randint(1, 99)
        fresh_mimir.constants["mimir//FULLIMPLOSSPROTECTIONBLOCKS"] = 10000 * random.randint(1, 999)
        return fresh_mimir

    @staticmethod
    def mimir_last_modification_key(name):
        return f'MimirLastChange:{name}'

    async def last_mimir_change(self, name: str) -> Optional[MimirChange]:
        if not name:
            return
        data = await self.deps.db.redis.get(self.mimir_last_modification_key(name))
        if data:
            return MimirChange.from_json(data)

    async def _save_mimir_change(self, change: MimirChange):
        try:
            await self.deps.db.redis.set(self.mimir_last_modification_key(change.name), change.as_json_string)
        except Exception as e:
            self.logger.error(f'Failed to save last Mimir change: {e}')

    async def on_data(self, sender: ConstMimirFetcher, data: Tuple[ThorConstants, ThorMimir]):
        _, fresh_mimir = data

        # fresh_mimir = self._dbg_randomize_mimir(fresh_mimir)  # fixme

        if not fresh_mimir.constants:
            return

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
                await self._save_mimir_change(change)

        if changes:
            await self.deps.broadcaster.notify_preconfigured_channels(
                self.deps.loc_man,
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
