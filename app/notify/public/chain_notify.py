import json
import random
from typing import Dict, NamedTuple, List

from api.aionode.types import ThorChainInfo
from lib.cooldown import Cooldown
from lib.date_utils import MINUTE
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.utils import WithLogger

EXCLUDE_CHAINS_FROM_HALTED = ('BNB',)


class AlertChainHalt(NamedTuple):
    changed_chains: List[ThorChainInfo]


class TradingHaltedNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

        self.cooldown_sec = self.deps.cfg.as_interval('chain_halt_state.cooldown', 10 * MINUTE)
        self.hit_count_before_cooldown = 5

    def _dbg_randomize_chain_dic_halted(self, data: Dict[str, ThorChainInfo]):
        for item in data.values():
            item.halted = random.uniform(0, 1) > 0.5
        return data

    def _make_spam_control(self, chain: str):
        return Cooldown(
            self.deps.db, f'TradingHalted:{chain}',
            self.cooldown_sec, max_times=self.hit_count_before_cooldown
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

        # do not show Excluded chains
        data = {chain: v for chain, v in data.items() if chain not in EXCLUDE_CHAINS_FROM_HALTED}

        self.deps.chain_info = data

        for chain, new_info in data.items():
            new_info: ThorChainInfo
            if new_info.is_ok:
                old_info = await self._get_saved_chain_state(chain)
                if old_info and old_info.is_ok:
                    if old_info.halted != new_info.halted:
                        if await self._can_notify_on_chain(chain):
                            changed_chains.append(new_info)

                await self._save_chain_state(new_info)
                self._update_global_state(chain, new_info.halted)

        if changed_chains:
            await self.pass_data_to_listeners(AlertChainHalt(changed_chains))

            # after notification trigger the involved cooldown timers
            for chain_info in changed_chains:
                chain_info: ThorChainInfo
                await self._make_spam_control(chain_info.chain).do()

    KEY_CHAIN_HALTED = 'Chain:LastInfo'

    def _update_global_state(self, chain, is_halted):
        if chain:
            halted_set = self.deps.halted_chains

            if chain in EXCLUDE_CHAINS_FROM_HALTED:
                is_halted = False  # do not show it

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
