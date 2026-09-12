import json
import random
from typing import Dict, NamedTuple, List, Optional

from api.aionode.types import ThorChainInfo
from lib.cooldown import Cooldown
from lib.date_utils import MINUTE, HOUR, now_ts
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.chains import ChainAspect, AspectState, ChainAspectStatus, ChainStatusRow, ChainStatusTable


class AlertChainHalt(NamedTuple):
    changed_chains: List[ThorChainInfo]
    status_table: Optional[ChainStatusTable] = None


class ChainIncidentTracker(WithLogger):
    """
    Remembers when every chain aspect (scanning/trading/LP/signing) was last seen paused.
    The infographic uses it to mark recently recovered aspects as "unstable" (a yellow dot),
    even though they are available again right now.
    """

    KEY_LAST_INCIDENT = 'Chain:LastIncident'

    def __init__(self, deps: DepContainer, window_sec: float):
        super().__init__()
        self.deps = deps
        self.window_sec = window_sec

    @staticmethod
    def _field(chain: str, aspect: str):
        return f'{chain}:{aspect}'

    async def register(self, paused_flags: Dict[str, Dict[str, Optional[bool]]]):
        """
        Save "now" as the last incident timestamp for every aspect that is paused at the moment.
        """
        now = now_ts()
        fresh = {
            self._field(chain, aspect): now
            for chain, aspects in paused_flags.items()
            for aspect, paused in aspects.items()
            if paused
        }
        if not fresh:
            return

        db = await self.deps.db.get_redis()
        await db.hset(self.KEY_LAST_INCIDENT, mapping={k: str(v) for k, v in fresh.items()})

    async def recent_incidents(self) -> Dict[str, float]:
        """
        Returns "{chain}:{aspect}" -> seconds since the last incident, for recent incidents only.
        Outdated records are pruned along the way, so the hash does not grow forever.
        """
        db = await self.deps.db.get_redis()
        raw = await db.hgetall(self.KEY_LAST_INCIDENT)
        if not raw:
            return {}

        now, recent, outdated = now_ts(), {}, []
        for field, raw_ts in raw.items():
            try:
                ago = now - float(raw_ts)
            except (TypeError, ValueError):
                outdated.append(field)
                continue

            if 0 <= ago <= self.window_sec:
                recent[field] = ago
            else:
                outdated.append(field)

        if outdated:
            await db.hdel(self.KEY_LAST_INCIDENT, *outdated)

        return recent

    def aspect_status(self, chain: str, aspect: str, paused: Optional[bool],
                      recent: Dict[str, float]) -> ChainAspectStatus:
        if paused is None:
            return ChainAspectStatus(AspectState.UNKNOWN)
        elif paused:
            return ChainAspectStatus(AspectState.PAUSED)
        else:
            return ChainAspectStatus(AspectState.AVAILABLE, recent.get(self._field(chain, aspect)))


class TradingHaltedNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

        self.cooldown_sec = self.deps.cfg.as_interval('chain_halt_state.cooldown', 10 * MINUTE)
        self.max_hits_before_cd = self.deps.cfg.as_int('chain_halt_state.max_hits_before_cd', 5)
        recent_window = self.deps.cfg.as_interval('chain_halt_state.recent_incident_window', 2 * HOUR)
        self.incident_tracker = ChainIncidentTracker(deps, recent_window)
        self.logger.info(f'Chain Halt cooldown: {self.cooldown_sec} sec, max hits: {self.max_hits_before_cd}, '
                         f'recent incident window: {recent_window} sec')

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

    def _paused_flags(self, info: ThorChainInfo) -> Dict[str, Optional[bool]]:
        """
        Which aspects of this chain are paused right now? None means "no data" (mimir is not loaded yet).
        """
        chain = info.chain.upper()
        mimir = self.deps.mimir_const_holder
        mimir_loaded = mimir is not None and mimir.is_loaded

        # Inbound addresses do not report signing halts, so it comes from Mimir only
        signing_paused = bool(mimir.get_constant(f'HALTSIGNING{chain}')) if mimir_loaded else None

        # The global PAUSELP switch is not reflected in `chain_lp_actions_paused` either
        lp_paused = info.chain_lp_actions_paused or (bool(mimir.get_constant('PAUSELP')) if mimir_loaded else False)

        return {
            ChainAspect.SCANNING: info.halted,
            ChainAspect.TRADING: info.chain_trading_paused or info.global_trading_paused,
            ChainAspect.LP: lp_paused,
            ChainAspect.SIGNING: signing_paused,
        }

    async def build_status_table(self, data: Dict[str, ThorChainInfo],
                                 changed_chains: List[ThorChainInfo] = None) -> ChainStatusTable:
        """
        Builds the full network status snapshot for the infographic: one row per chain,
        one cell per aspect, plus "recently recovered" marks from the incident tracker.
        """
        paused_flags = {
            chain: self._paused_flags(info)
            for chain, info in data.items() if info.is_ok
        }

        await self.incident_tracker.register(paused_flags)
        recent = await self.incident_tracker.recent_incidents()

        changed_names = {c.chain for c in changed_chains} if changed_chains else set()

        rows = [
            ChainStatusRow(
                chain=chain,
                aspects={
                    aspect: self.incident_tracker.aspect_status(chain, aspect, paused, recent)
                    for aspect, paused in aspects.items()
                },
                changed=chain in changed_names,
            )
            for chain, aspects in sorted(paused_flags.items())
        ]

        return ChainStatusTable(rows=rows, recent_window_sec=self.incident_tracker.window_sec)

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

        # this also keeps the incident history up to date, so it must run on every tick
        status_table = await self.build_status_table(data, changed_chains)

        if changed_chains:
            await self.pass_data_to_listeners(AlertChainHalt(changed_chains, status_table))

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
