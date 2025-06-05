from typing import NamedTuple, List, Optional

from api.aionode.types import ThorCoinDec
from jobs.scanner.util import thor_decode_amount_field, pubkey_to_thor_address
from lib.utils import safe_get


class ThorEvent(NamedTuple):
    attrs: dict

    def get(self, key, default=None):
        return self.attrs.get(key, default)

    @staticmethod
    def _decode_combined_value_asset(d, v):
        d['_amount'], d['_asset'] = thor_decode_amount_field(v)

    @classmethod
    def from_dict(cls, d, height=0):
        if coin := d.get('coin'):
            cls._decode_combined_value_asset(d, coin)
        elif amount := d.get('amount'):
            # if there are any letters in "amount"
            if any(c.isalpha() for c in amount):
                cls._decode_combined_value_asset(d, amount)

        o = cls(d)
        if height:
            o.height = height
        return o

    @property
    def amount(self):
        return self.attrs.get('_amount', 0)

    @property
    def asset(self):
        return self.attrs.get('_asset', '')

    @property
    def type(self):
        return self.attrs.get('type', '')

    @property
    def height(self):
        return int(self.attrs.get('_height', 0))

    @height.setter
    def height(self, value):
        self.attrs['_height'] = int(value)


class ThorTxMessage(NamedTuple):
    attrs: dict

    MsgObservedTxIn = '/types.MsgObservedTxIn'
    MsgDeposit = '/types.MsgDeposit'
    MsgSend = '/types.MsgSend'
    MsgSendCosmos = '/cosmos.bank.v1beta1.MsgSend'
    MsgExecuteContract = '/cosmwasm.wasm.v1.MsgExecuteContract'
    MsgObservedTxQuorum = '/types.MsgObservedTxQuorum'  # new!

    @property
    def is_send(self):
        return self.type == self.MsgSend or self.type == self.MsgSendCosmos

    @property
    def is_contract(self):
        return self.type == self.MsgExecuteContract

    @property
    def is_quorum(self):
        return self.type == self.MsgObservedTxQuorum

    @property
    def txs(self) -> List[dict]:
        return self.attrs.get('txs', [])

    @property
    def coins(self) -> List[dict]:
        return self.attrs.get('coins', [])

    def __bool__(self):
        return bool(self.attrs)

    @property
    def type(self):
        return self.attrs.get('@type', '')

    def get(self, key, default=None):
        return self.attrs.get(key, default)

    @classmethod
    def from_dict(cls, d):
        return cls(d)

    @property
    def memo(self):
        return self.attrs.get('memo', '')

    @property
    def contract_message(self):
        return self.attrs.get('msg') if self.is_contract else None

    @property
    def contract_funds(self):
        return self.attrs.get('funds', []) if self.is_contract else None

    @property
    def contract_address(self):
        return self.attrs.get('contract', None) if self.is_contract else None


class ThorObservedTx(NamedTuple):
    tx_id: str
    chain: str
    from_address: str
    to_address: str
    coins: List[ThorCoinDec]
    gas: List[ThorCoinDec]
    memo: str
    status: str
    out_hashes: List[str]
    block_height: int
    finalise_height: int
    aggregator: str
    aggregator_target: str
    aggregator_target_limit: Optional[int] = None
    is_inbound: bool = False
    original: dict = None

    @property
    def is_outbound(self):
        return not self.is_inbound

    @classmethod
    def from_dict(cls, d):
        tx = d.get('tx', {})
        return cls(
            tx_id=tx.get('id'),
            chain=tx.get('chain'),
            from_address=tx.get('from_address'),
            to_address=tx.get('to_address'),
            coins=[
                ThorCoinDec.from_json(j) for j in tx.get('coins', [])
            ],
            gas=[
                ThorCoinDec.from_json(j) for j in tx.get('gas', [])
            ],
            memo=tx.get('memo'),
            status=d.get('status', ''),
            out_hashes=d.get('out_hashes', []),
            block_height=d.get('block_height', 0),
            finalise_height=d.get('finalise_height', 0),
            aggregator=d.get('aggregator', ''),
            aggregator_target=d.get('aggregator_target', ''),
            aggregator_target_limit=d.get('aggregator_target_limit'),
            is_inbound=d.get('__is_inbound', False),
            original=d,
        )


class ThorSignerInfo(NamedTuple):
    public_key: str
    mode: dict
    sequence: int

    @property
    def address(self):
        return pubkey_to_thor_address(self.public_key)

    @classmethod
    def from_dict(cls, d):
        return cls(
            public_key=safe_get(d, 'public_key', 'key'),
            mode=d.get('mode_info', {}),
            sequence=int(d.get('sequence', 0)),
        )


class NativeThorTx(NamedTuple):
    tx_hash: str
    code: int
    events: List[ThorEvent]
    height: int
    original: dict
    signers: List[ThorSignerInfo]
    messages: List[ThorTxMessage]
    log: str = ''
    memo: str = ''
    timestamp: int = 0

    @property
    def error_message(self):
        return self.log if self.is_error else ''

    @property
    def first_signer_address(self):
        return self.signers[0].address if self.signers else None

    @classmethod
    def from_dict(cls, d, height, timestamp=0):
        result = d.get('result', {})
        tx = d.get('tx', {})
        signers_raw = safe_get(tx, 'auth_info', 'signer_infos')
        signers = [ThorSignerInfo.from_dict(s) for s in signers_raw] if isinstance(signers_raw, list) else []
        body = tx.get('body', {})

        if "messages" in body:
            # old format
            messages_raw = body.get('messages')
        else:
            # new format for Quorum Txs
            messages_raw = tx.get('messages', [])
        messages = [ThorTxMessage.from_dict(m) for m in messages_raw]

        return cls(
            tx_hash=d['hash'],
            code=result['code'],
            height=height,
            events=[ThorEvent.from_dict(attrs, height=height) for attrs in result.get('events', [])],
            log=result.get('log', ''),
            original=d,
            signers=signers,
            memo=body.get('memo', ''),
            messages=messages,
            timestamp=timestamp,
        )

    @property
    def is_success(self):
        return self.code == 0

    @property
    def is_error(self):
        return not self.is_success

    @property
    def first_message(self) -> Optional[ThorTxMessage]:
        return self.messages[0] if self.messages else None

    def find_events_by_type(self, ev_type):
        return [e for e in self.events if e.type == ev_type]
