import json
import logging
import random
from typing import Dict

from aiothornode.types import ThorChainInfo

from localization import BaseLocalization
from services.jobs.fetch.base import INotified
from services.lib.depcont import DepContainer


class TradingHaltedNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = logging.getLogger(self.__class__.__name__)
        # self.spam_cd = Cooldown(self.deps.db, 'TradingHalted', 30 * MINUTE)

    def _dbg_randomize_chain_dic_halted(self, data: Dict[str, ThorChainInfo]):
        for item in data.values():
            item.halted = random.uniform(0, 1) > 0.5
        return data

    async def on_data(self, sender, data: Dict[str, ThorChainInfo]):
        # data = self._dbg_randomize_chain_dic_halted(data)

        changed_chains = []

        for chain, new_info in data.items():
            new_info: ThorChainInfo
            if new_info.is_ok:
                old_info = await self._get_saved_chain_state(chain)
                if old_info and old_info.is_ok:
                    if old_info.halted != new_info.halted:
                        changed_chains.append(new_info)

                await self._save_chain_state(new_info)
                self._update_global_state(chain, new_info.halted)

        if changed_chains:
            await self.deps.broadcaster.notify_preconfigured_channels(
                self.deps.loc_man,
                BaseLocalization.notification_text_trading_halted_multi,
                changed_chains
            )

    KEY_CHAIN_HALTED = 'Chain:LastInfo'

    def _update_global_state(self, chain, is_halted):
        if chain:
            halted_set = self.deps.halted_chains
            if is_halted:
                halted_set.add(chain)
            elif chain in halted_set:
                halted_set.remove(chain)

    async def _get_saved_chain_state(self, chain):
        if not chain:
            self.logger.error('no "chain"!')
            return

        db = await self.deps.db.get_redis()
        raw_data = await db.hget(self.KEY_CHAIN_HALTED, chain)
        try:
            j = json.loads(raw_data)
            return ThorChainInfo.from_json(j)
        except (TypeError, ValueError):
            return None

    async def _save_chain_state(self, c: ThorChainInfo):
        if not c or not c.chain:
            self.logger.error('empty Chain Info')
            return

        data = json.dumps({
            'chain': c.chain,
            'pub_key': c.pub_key,
            'address': c.address,
            'router': c.router,
            'halted': c.halted,
            'gas_rate': c.gas_rate
        })

        db = await self.deps.db.get_redis()
        await db.hset(self.KEY_CHAIN_HALTED, c.chain, data)
