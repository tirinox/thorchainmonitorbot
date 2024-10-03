from typing import NamedTuple, Dict

from lib.constants import RUNE_SUPPLY_AFTER_SWITCH, RUNE_IDEAL_SUPPLY, RUNE_BURNT_ADR_12, ThorRealms
from lib.date_utils import DAY


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


class RuneBurnEvent(NamedTuple):
    curr_max_rune: float
    prev_max_rune: float
    period_seconds: float = DAY
