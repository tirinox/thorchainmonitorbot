from dataclasses import dataclass
from datetime import datetime


@dataclass
class KilledRuneEntry:
    timestamp: float = 0
    block_id: int = 0
    # estimates:
    unkilled_unswitched_rune: float = 0
    total_killed: float = 0
    killed_switched: float = 0

    @classmethod
    def from_flipside_json(cls, j):
        try:
            it = cls(
                # timestamp=datetime.strptime(j.get('BLOCK_TIMESTAMP'), '%Y-%m-%d %H:%M:%S.%f').timestamp(),
                timestamp=datetime.strptime(j.get('DATE'), '%Y-%m-%d').timestamp(),
                block_id=int(j.get('BLOCK_ID', 0)),
                unkilled_unswitched_rune=float(j.get('UNKILLED_UNSWITCHED_ESTIMATE', 0.0)),
                total_killed=float(j.get('TOTAL_KILLED_ESTIMATE', 0.0)),
                killed_switched=float(j.get('KILLED_SWITCHED', 0.0))
            )
            return it
        except (TypeError, ValueError):
            pass
