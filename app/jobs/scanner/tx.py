from typing import NamedTuple, List, Optional

from jobs.scanner.util import thor_decode_amount_field, pubkey_to_thor_address
from lib.utils import safe_get


class ThorEvent(NamedTuple):
    attrs: dict

    def get(self, key, default=None):
        return self.attrs.get(key, default)

    def __len__(self):
        return len(self.attrs)

    def __getitem__(self, key):
        return self.attrs[key]

    def __iter__(self):
        return iter(self.attrs)

    def __repr__(self):
        return f"ThorEvent({self.attrs})"

    @classmethod
    def from_dict(cls, d, height=0):
        for key in ('coin', 'amount'):
            if key in d:
                d['_amount'], d['_asset'] = thor_decode_amount_field(d[key])

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
        return self.attrs.get('_height', 0)

    @height.setter
    def height(self, value):
        self.attrs['_height'] = value


class ThorTxMessage(NamedTuple):
    attrs: dict

    MsgObservedTxIn = '/types.MsgObservedTxIn'
    MsgDeposit = '/types.MsgDeposit'
    MsgSend = '/types.MsgSend'
    MsgSendCosmos = '/cosmos.bank.v1beta1.MsgSend'

    @property
    def is_send(self):
        return self.type == self.MsgSend or self.type == self.MsgSendCosmos

    @property
    def txs(self) -> List[dict]:
        return self.attrs.get('txs', [])

    @property
    def coins(self) -> List[dict]:
        return self.attrs.get('coins', [])

    def __len__(self):
        return len(self.txs)

    def __getitem__(self, key):
        return self.attrs[key]

    def __iter__(self):
        return iter(self.attrs)

    @property
    def type(self):
        return self.attrs.get('@type', '')

    def get(self, key, default=None):
        return self.attrs.get(key, default)

    @classmethod
    def from_dict(cls, d):
        return cls(d)

    @property
    def deep_memo(self):
        if 'txs' in self.attrs:
            for tx in self.attrs['txs']:
                if memo := safe_get(tx, 'tx', 'memo'):
                    return memo
        elif memo := self.attrs.get('memo'):
            return memo


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
    this_memo: str = ''

    @property
    def error_message(self):
        return self.log if self.is_error else ''

    @property
    def first_signer_address(self):
        return self.signers[0].address if self.signers else None

    @property
    def deep_memo(self):
        """
        Tries to get memo from inside TXs messages, for instance "/types.MsgObservedTxIn" has memo in txs[].tx.memo
        """
        if self.this_memo:
            return self.this_memo

        for msg in self.messages:
            if memo := msg.deep_memo:
                return memo
        return ''

    @classmethod
    def from_dict(cls, d, height):
        result = d.get('result', {})
        tx = d.get('tx', {})
        signers_raw = safe_get(tx, 'auth_info', 'signer_infos')
        signers = [ThorSignerInfo.from_dict(s) for s in signers_raw]
        body = tx.get('body', {})
        messages = [ThorTxMessage.from_dict(m) for m in body.get('messages', [])]
        return cls(
            tx_hash=d['hash'],
            code=result['code'],
            height=height,
            events=[ThorEvent.from_dict(attrs, height=height) for attrs in result.get('events', [])],
            log=result.get('log', ''),
            original=d,
            signers=signers,
            this_memo=body.get('memo', ''),
            messages=messages,
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
