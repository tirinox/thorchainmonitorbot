import json
import random
from typing import Dict, NamedTuple, List

from api.aionode.types import ThorChainInfo
from lib.cooldown import Cooldown
from lib.date_utils import MINUTE
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger


class AlertChainHalt(NamedTuple):
    changed_chains: List[ThorChainInfo]


class TradingHaltedNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

        self.cooldown_sec = self.deps.cfg.as_interval('chain_halt_state.cooldown', 10 * MINUTE)
        self.max_hits_before_cd = self.deps.cfg.as_int('chain_halt_state.max_hits_before_cd', 5)
        self.logger.info(f'Chain Halt cooldown: {self.cooldown_sec} sec, max hits: {self.max_hits_before_cd}')

    def _dbg_randomize_chain_dic_halted(self, data: Dict[str, ThorChainInfo]):
        for item in data.values():
            item.halted = random.uniform(0, 1) > 0.5
        return data

    def _make_spam_control(self, chain: str):
        return Cooldown(
            self.deps.db, f'TradingHalted:{chain}',
            self.cooldown_sec, max_times=self.max_hits_before_cd
        )

    async def _can_notify_on_chain(self, chain: str):
        if not chain:
            return False
        can_do = await self._make_spam_control(chain).can_do()
        if not can_do:
            self.logger.warning(f"Attention! {chain} halt state changed again, but spam control didn't let it through")
        return can_do

    async def on_data(self, sender, data: Dict[str, ThorChainInfo]):
        # data = self._dbg_randomize_chain_dic_halted(data)

        changed_chains = []

        for chain, new_info in data.items():
            new_info: ThorChainInfo
            if new_info.is_ok:
                old_info = await self._get_saved_chain_state(chain)
                if old_info and old_info.is_ok:
                    if old_info.halted != new_info.halted:
                        if await self._can_notify_on_chain(chain):
                            changed_chains.append(new_info)

                await self._save_chain_state(new_info)

        if changed_chains:
            await self.pass_data_to_listeners(AlertChainHalt(changed_chains))

            # after notification trigger the involved cooldown timers
            for chain_info in changed_chains:
                chain_info: ThorChainInfo
                await self._make_spam_control(chain_info.chain).do()

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

        data = json.dumps(c._asdict())
        db = await self.deps.db.get_redis()
        await db.hset(self.KEY_CHAIN_HALTED, c.chain, data)
