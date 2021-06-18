import json
import logging
from typing import Dict

from aiothornode.types import ThorChainInfo

from services.jobs.fetch.base import INotified
from services.lib.depcont import DepContainer


class TradingHaltedNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = logging.getLogger(self.__class__.__name__)
        # self.spam_cd = Cooldown(self.deps.db, 'TradingHalted', 30 * MINUTE)

    async def on_data(self, sender, data: Dict[str, ThorChainInfo]):
        changed_chains = []

        for chain, new_info in data.items():
            new_info: ThorChainInfo
            if new_info.is_ok:
                old_info = await self._get_saved_chain_state(chain)
                if old_info and old_info.is_ok:
                    if old_info.halted != new_info.halted:
                        changed_chains.append((chain, new_info.halted))

                await self._save_chain_state(new_info)

        if changed_chains:
            ...

    KEY_CHAIN_HALTED = 'Chain:LastInfo'

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
