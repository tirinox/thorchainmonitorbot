from dataclasses import dataclass
from datetime import datetime


@dataclass
class KilledRuneEntry:
    timestamp: float
    block_id: int
    # estimates:
    unkilled_unswitched_rune: float
    total_killed: float
    killed_switched: float

    @classmethod
    def from_flipside_json(cls, j):
        it = cls(
            timestamp=datetime.strptime(j.get('BLOCK_TIMESTAMP'), '%Y-%m-%d %H:%M:%S.%f').timestamp(),
            block_id=int(j.get('BLOCK_TIMESTAMP', 0)),
            unkilled_unswitched_rune=float(j.get('UNKILLED_UNSWITCHED_ESTIMATE', 0.0)),
            total_killed=float(j.get('TOTAL_KILLED_ESTIMATE', 0.0)),
            killed_switched=float(j.get('KILLED_SWITCHED', 0.0))
        )
        return it
