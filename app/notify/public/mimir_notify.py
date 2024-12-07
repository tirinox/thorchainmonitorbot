import json
from contextlib import suppress

from api.aionode.types import ThorMimir
from jobs.fetch.mimir import ConstMimirFetcher, MimirTuple
from lib.cooldown import Cooldown
from lib.date_utils import now_ts
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.utils import WithLogger
from models.mimir import MimirChange, AlertMimirChange
from models.mimir_naming import MIMIR_KEY_MAX_RUNE_SUPPLY

TOO_MANY_CHANGES = 10


class MimirChangedNotifier(INotified, WithDelegates, WithLogger):
    MIMIR_IGNORE_CHANGES = [
        MIMIR_KEY_MAX_RUNE_SUPPLY,  # ADR 17 burn rune
    ]

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.cd_sec_change = deps.cfg.as_interval('constants.mimir_change.cooldown')
        self.max_hits_before_cd = deps.cfg.as_int('constants.mimir_change.max_hits_before_cd')

    @staticmethod
    def mimir_last_modification_key(name):
        return f'MimirLastChangeTS:{name}'

    async def last_mimir_change_date(self, name: str) -> float:
        if not name:
            return 0
        with suppress(Exception):
            data = await self.deps.db.redis.get(self.mimir_last_modification_key(name))
            return float(data)
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

    async def on_data(self, sender: ConstMimirFetcher, data: MimirTuple):
        fresh_mimir = data.mimir
        node_mimir = data.node_mimir

        if not fresh_mimir or not fresh_mimir.constants:
            return

        await self._ensure_all_last_changes_in_holder(fresh_mimir)

        old_mimir = await self._get_saved_mimir_state(is_node_mimir=False)
        old_node_mimir = await self._get_saved_mimir_state(is_node_mimir=True)
        if not old_mimir:
            self.logger.warning('Mimir has not been saved yet. Waiting for the next tick...')
            await self._save_mimir_state(fresh_mimir.constants, is_node_mimir=False)
            await self._save_mimir_state(node_mimir, is_node_mimir=True)
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
                # test if value changed
                old_value = old_mimir[name]
                new_value = fresh_mimir[name]
                if old_value != new_value:
                    change_kind = MimirChange.VALUE_CHANGE
            elif name in fresh_const_names and name not in old_const_names:
                # test if there is new Mimir
                new_value = fresh_mimir[name]
                old_value = holder.get_hardcoded_const(name)
                change_kind = MimirChange.ADDED_MIMIR
            elif name not in fresh_const_names and name in old_const_names:
                # test if Mimir key deleted
                old_value = old_mimir[name]
                new_value = holder.get_hardcoded_const(name)
                change_kind = MimirChange.REMOVED_MIMIR

            if change_kind is not None:
                entry = self.deps.mimir_const_holder.get_entry(name)
                if entry:
                    node_mimir_ceased = name in old_node_mimir and name not in node_mimir
                    if node_mimir_ceased:
                        entry.source = entry.SOURCE_NODE_CEASED

                    change = MimirChange(change_kind, name, old_value, new_value, entry, timestamp)

                    if await self._will_pass(change):
                        changes.append(change)

                    await self._save_mimir_change_date(change)

        if fresh_mimir and fresh_mimir.constants:
            await self._save_mimir_state(fresh_mimir.constants, is_node_mimir=False)
            await self._save_mimir_state(node_mimir, is_node_mimir=True)

        if changes:
            if len(changes) > TOO_MANY_CHANGES:
                self.deps.emergency.report(self.logger.name, f'Too many Mimir changes: {len(changes)}')
                return

            await self.pass_data_to_listeners(AlertMimirChange(
                changes, self.deps.mimir_const_holder
            ))

    DB_KEY_MIMIR_LAST_STATE = 'Mimir:LastState'
    DB_KEY_NODE_MIMIR_LAST_STATE = 'Mimir:Node:LastState'

    async def _get_saved_mimir_state(self, is_node_mimir: bool):
        db = await self.deps.db.get_redis()
        key = self.DB_KEY_NODE_MIMIR_LAST_STATE if is_node_mimir else self.DB_KEY_MIMIR_LAST_STATE
        raw_data = await db.get(key)
        try:
            j = json.loads(raw_data)
            return j if is_node_mimir else ThorMimir.from_json(j)
        except (TypeError, ValueError):
            return None

    async def _save_mimir_state(self, c: dict, is_node_mimir: bool):
        data = json.dumps(c)
        db = await self.deps.db.get_redis()
        key = self.DB_KEY_NODE_MIMIR_LAST_STATE if is_node_mimir else self.DB_KEY_MIMIR_LAST_STATE
        await db.set(key, data)

    async def _will_pass(self, c: MimirChange):
        if c.is_automatic_to_automatic:
            return False

        if c.name in self.MIMIR_IGNORE_CHANGES:
            return False

        cd = Cooldown(self.deps.db, f"MimirChange:{c.entry.name}", self.cd_sec_change,
                      max_times=self.max_hits_before_cd)
        if await cd.can_do():
            await cd.do()
            return True
        else:
            self.logger.warning(f'Mimir {c.entry.name!r} changes too often! Ignore.')
            return False
