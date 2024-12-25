from typing import NamedTuple, Dict

from lib.constants import RUNE_SUPPLY_AFTER_SWITCH, RUNE_IDEAL_SUPPLY, RUNE_BURNT_ADR_12, ThorRealms
from lib.date_utils import DAY, now_ts
from lib.money import calculate_yearly_growth_from_values


class RuneHoldEntry(NamedTuple):
    address: str
    amount: int
    name: str
    realm: str

    def add_amount(self, amount):
        return self._replace(amount=self.amount + amount)


class RuneCirculatingSupply(NamedTuple):
    circulating: int
    total: int
    maximum: int
    holders: Dict[str, RuneHoldEntry]

    @classmethod
    def zero(cls):
        return cls(0, 0, 0, {})

    def set_holder(self, h: RuneHoldEntry):
        self.holders[h.address] = h

    @property
    def killed_switched(self):
        return RUNE_IDEAL_SUPPLY - RUNE_SUPPLY_AFTER_SWITCH

    @property
    def burnt_rune_from_income(self):
        return RUNE_IDEAL_SUPPLY - self.maximum

    @property
    def lending_burnt_rune(self):
        return RUNE_SUPPLY_AFTER_SWITCH - self.total - self.adr12_burnt_rune

    @property
    def adr12_burnt_rune(self):
        return RUNE_BURNT_ADR_12

    @property
    def total_burnt_rune(self):
        return RUNE_SUPPLY_AFTER_SWITCH - self.total

    def find_by_realm(self, realms, join_by_name=False):
        if isinstance(realms, str):
            realms = (realms,)
        items = [h for h in self.holders.values() if h.realm in realms]
        if join_by_name:
            name_dict = {}
            for item in items:
                if item.name in name_dict:
                    name_dict[item.name] = name_dict[item.name].add_amount(item.amount)
                else:
                    name_dict[item.name] = item
            return list(name_dict.values())
        return items

    def total_rune_in_realm(self, realms):
        return sum(h.amount for h in self.find_by_realm(realms))

    def __repr__(self) -> str:
        return f"RuneCirculatingSupply(circulating={self.circulating}, total={self.total}, holders={len(self.holders)})"

    @property
    def in_cex(self):
        return self.total_rune_in_realm(ThorRealms.CEX)

    @property
    def in_cex_percent(self):
        return self.in_cex / self.total * 100

    @property
    def treasury(self):
        return self.total_rune_in_realm(ThorRealms.TREASURY)

    @property
    def treasury_percent(self):
        return self.treasury / self.total * 100

    @property
    def in_reserves(self):
        return self.total_rune_in_realm((ThorRealms.RESERVES, ThorRealms.STANDBY_RESERVES))

    @property
    def bonded(self):
        return self.total_rune_in_realm(ThorRealms.BONDED)

    @property
    def bonded_percent(self):
        return self.bonded / self.total * 100

    @property
    def pooled(self):
        return self.total_rune_in_realm(ThorRealms.LIQ_POOL)

    @property
    def pooled_percent(self):
        return self.pooled / self.total * 100

    @property
    def pol(self):
        return self.total_rune_in_realm(ThorRealms.POL)

    @property
    def pol_percent(self):
        return self.pol / self.total * 100

    @property
    def runepool(self):
        return self.total_rune_in_realm(ThorRealms.RUNEPOOL)

    @property
    def runepool_percent(self):
        return self.runepool / self.total * 100

    @property
    def working(self):
        return self.bonded + self.pooled


class EventRuneBurn(NamedTuple):
    curr_max_rune: float
    prev_max_rune: float
    points: list
    usd_per_rune: float
    system_income_burn_percent: float
    period_seconds: float = DAY
    start_ts: int = 0
    tally_days: int = 7
    circulating_suppy: float = 1

    @property
    def total_burned_rune(self):
        return RUNE_IDEAL_SUPPLY - self.curr_max_rune

    @property
    def total_burned_usd(self):
        return self.total_burned_rune * self.usd_per_rune

    @property
    def time_passed_sec(self):
        return now_ts() - self.start_ts

    @property
    def yearly_burn_prediction(self):
        return self.deflation_percent * self.curr_max_rune / 100.0

    @property
    def delta_rune(self):
        return self.prev_max_rune - self.curr_max_rune

    @property
    def delta_usd(self):
        return self.delta_rune * self.usd_per_rune

    @property
    def deflation_percent(self):
        pct = calculate_yearly_growth_from_values(self.curr_max_rune, self.prev_max_rune, self.tally_days)
        return -pct

    @property
    def last_24h_burned_rune(self):
        return self.points[-1][1] if len(self.points) > 0 else 0

    @property
    def last_24h_burned_usd(self):
        return self.last_24h_burned_rune * self.usd_per_rune
