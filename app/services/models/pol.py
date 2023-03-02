from typing import NamedTuple

from aiothornode.types import ThorPOL


class EventPOL(NamedTuple):
    current: ThorPOL
