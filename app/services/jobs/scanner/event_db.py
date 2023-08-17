import json
from typing import NamedTuple, List, Optional

from aioredis import Redis

from proto.access import DecodedEvent
from services.lib.db import DB
from services.lib.memo import THORMemo
from services.lib.money import is_rune_asset
from services.models.s_swap import TypeEventSwapAndOut, parse_swap_and_out_event, EventStreamingSwap


class SwapProps(NamedTuple):
    attrs: dict
    events: List[TypeEventSwapAndOut]
    memo: THORMemo

    @classmethod
    def restore_events_from_tx_status(cls, attrs):
        """
            foo = await self.read_tx_status(swap_ev.tx_id)
            foo_ev = self.restore_events_from_tx_status(foo)
        """
        results = []
        key: str
        for key, value in attrs.items():
            if key.startswith('ev_'):
                raw_dict = json.loads(value)
                event = DecodedEvent.from_dict_our(raw_dict)
                swap_ev = parse_swap_and_out_event(event)
                results.append(swap_ev)

        return cls(
            attrs,
            results,
            memo=THORMemo.parse_memo(attrs.get('memo', ''))
        )

    @property
    def is_streaming(self):
        return bool(self.attrs.get('is_streaming', False))

    def find_event(self, klass) -> Optional[TypeEventSwapAndOut]:
        return next((e for e in self.events if isinstance(e, klass)), None)

    @property
    def is_streaming_finished(self):
        ss = self.find_event(EventStreamingSwap)
        return ss and ss.streaming_swap_count == ss.streaming_swap_quantity > 1

    @property
    def is_native_outbound(self):
        out_asset = self.memo.asset
        return '/' in out_asset or is_rune_asset(out_asset)


class EventDatabase:
    def __init__(self, db: DB):
        self.db = db

    @staticmethod
    def key_to_tx(tx_id):
        return f'tx:tracker:{tx_id}'

    async def read_tx_status(self, tx_id) -> SwapProps:
        r: Redis = await self.db.get_redis()
        props = await r.hgetall(self.key_to_tx(tx_id))
        return SwapProps.restore_events_from_tx_status(props)

    @staticmethod
    def _convert_type(v):
        if isinstance(v, bool):
            return 1 if v else 0
        elif isinstance(v, (int, float, str, bytes)):
            return v
        else:
            try:
                return json.dumps(v)
            except TypeError:
                return str(v)

    async def write_tx_status(self, tx_id, mapping):
        if mapping:
            r: Redis = await self.db.get_redis()
            kwargs = {k: self._convert_type(v) for k, v in mapping.items()}
            await r.hset(self.key_to_tx(tx_id), mapping=kwargs)

    async def write_tx_status_kw(self, tx_id, **kwargs):
        await self.write_tx_status(tx_id, kwargs)
