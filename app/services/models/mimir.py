from dataclasses import dataclass

from services.models.base import BaseModelMixin


@dataclass
class MimirChange(BaseModelMixin):
    kind: str
    name: str
    old_value: str
    new_value: str
    timestamp: float

    VALUE_CHANGE = '~'
    ADDED_MIMIR = '+'
    REMOVED_MIMIR = '-'

    def __post_init__(self):
        self.timestamp = float(self.timestamp)
