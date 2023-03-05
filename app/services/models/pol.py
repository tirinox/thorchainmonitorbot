from typing import NamedTuple, List, Optional

from aiothornode.types import ThorPOL

from services.models.pool_member import PoolMemberDetails


class EventPOL(NamedTuple):
    current: ThorPOL
    membership: List[PoolMemberDetails]
    previous: Optional[ThorPOL] = None
