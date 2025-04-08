from typing import NamedTuple

from jobs.scanner.tx import ThorObservedTx


class EventRujiSwitch(NamedTuple):
    tx: ThorObservedTx
