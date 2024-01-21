import base64
import datetime
import re
from hashlib import sha256
from typing import List, NamedTuple

import ujson
from dateutil.parser import parse as date_parser

THOR_BASE_MULT = 10 ** 8
THOR_BASE_MULT_INV = 1.0 / THOR_BASE_MULT


def thor_to_float(x) -> float:
    return int(x) * THOR_BASE_MULT_INV


def float_to_thor(x: float) -> int:
    return int(x * THOR_BASE_MULT)


class ThorException(Exception):
    def __init__(self, j, *args) -> None:
        super().__init__(*args)
        if j and isinstance(j, dict):
            self.code = j.get('code', '')
            self.message = j.get('message', '')
            self.details = j.get('details', [])
        else:
            self.code = -10000
            self.message = 'Failed to decode the error'
            self.details = [
                repr(j)
            ]


class ThorQueue(NamedTuple):
    outbound: int = 0
    swap: int = 0
    internal: int = 0
    scheduled_outbound_value: int = 0

    @classmethod
    def from_json(cls, j):
        return cls(
            outbound=int(j.get('outbound', -1)),
            swap=int(j.get('swap', -1)),
            internal=int(j.get('internal', -1)),
            scheduled_outbound_value=int(j.get('scheduled_outbound_value', -1)),
        )

    @property
    def total(self):
        return int(self.outbound) + int(self.swap) + int(self.internal)


class ThorNodeAccount(NamedTuple):
    STATUS_STANDBY = 'standby'
    STATUS_ACTIVE = 'active'
    STATUS_READY = 'ready'
    STATUS_WHITELISTED = 'whitelisted'
    STATUS_UNKNOWN = 'unknown'
    STATUS_DISABLED = 'disabled'

    node_address: str = 'thor?'
    status: str = ''
    pub_key_set: dict = None
    validator_cons_pub_key: str = ''
    bond: int = 0
    active_block_height: int = 0
    bond_address: str = ''
    status_since: int = ''
    signer_membership: list = None
    requested_to_leave: bool = False
    forced_to_leave: bool = False
    leave_height: int = 0
    ip_address: str = ''
    version: str = ''
    slash_points: int = 0
    jail: dict = None
    current_award: int = ''
    observe_chains: list = None
    preflight_status: dict = None
    bond_providers: dict = None

    @classmethod
    def from_json(cls, j):
        bond = int(j.get('total_bond', 0)) or int(j.get('bond', 0))
        node_operator_address = str(j.get('node_operator_address', '')) or str(j.get('bond_address', ''))

        return cls(
            node_address=str(j.get('node_address', '')),
            status=str(j.get('status', '')),
            pub_key_set=j.get('pub_key_set'),
            validator_cons_pub_key=str(j.get('validator_cons_pub_key', '')),
            bond=bond,
            active_block_height=int(j.get('active_block_height', 0)),
            bond_address=node_operator_address,
            status_since=int(j.get('status_since', 0)),
            signer_membership=j.get('signer_membership', []),
            requested_to_leave=bool(j.get('requested_to_leave', False)),
            forced_to_leave=bool(j.get('forced_to_leave', False)),
            leave_height=int(j.get('leave_height', 0)),
            ip_address=str(j.get('ip_address', '')),
            version=str(j.get('version', '')),
            slash_points=int(j.get('slash_points', 0)),
            jail=j.get('jail', {}),
            current_award=int(j.get('current_award', 0)),
            observe_chains=j.get('observe_chains', []),
            preflight_status=j.get('preflight_status', {}),
            bond_providers=j.get('bond_providers', {})
        )

    @property
    def preflight_status_reason_and_code(self):
        status = self.preflight_status.get('status', '').lower()
        reason = self.preflight_status.get('reason', '')
        code = self.preflight_status.get('code', 0)
        return status, reason, code

    @property
    def is_good(self):
        status = self.status.lower()
        return (
                status in (self.STATUS_ACTIVE, self.STATUS_WHITELISTED) and
                not self.requested_to_leave and not self.forced_to_leave and self.ip_address
        )


class ThorLastBlock(NamedTuple):
    chain: str = ''
    last_observed_in: int = 0
    last_signed_out: int = 0
    thorchain: int = 0

    @classmethod
    def from_json(cls, j):
        return cls(
            chain=j.get('chain', ''),
            last_observed_in=j.get('last_observed_in', 0) if 'last_observed_in' in j else j.get('lastobservedin'),
            last_signed_out=j.get('last_signed_out', 0) if 'last_signed_out' in j else j.get('lastsignedout'),
            thorchain=j.get('thorchain', 0)
        )


class ThorPool(NamedTuple):
    balance_asset: int = 0
    balance_rune: int = 0
    asset: str = ''
    lp_units: int = 0
    pool_units: int = 0
    status: str = ''
    synth_units: int = 0
    decimals: int = 0
    error: str = ''
    pending_inbound_rune: int = 0
    pending_inbound_asset: int = 0
    savers_depth: int = 0
    savers_units: int = 0
    synth_mint_paused: bool = False
    synth_supply: int = 0

    STATUS_AVAILABLE = 'Available'
    STATUS_BOOTSTRAP = 'Bootstrap'
    STATUS_ENABLED = 'Enabled'

    @property
    def assets_per_rune(self):
        return self.balance_asset / self.balance_rune

    @property
    def runes_per_asset(self):
        return self.balance_rune / self.balance_asset

    @classmethod
    def from_json(cls, j):
        return cls(
            balance_asset=int(j.get('balance_asset', 0)),
            balance_rune=int(j.get('balance_rune', 0)),
            asset=j.get('asset', ''),
            lp_units=int(j.get('LP_units', 0)),
            pool_units=int(j.get('pool_units', 0)),  # Sum of LP_units and synth_units
            status=j.get('status', cls.STATUS_BOOTSTRAP),
            synth_units=int(j.get('synth_units', 0)),
            synth_supply=int(j.get('synth_supply', 0)),
            decimals=int(j.get('decimals', 0)),
            error=j.get('error', ''),
            pending_inbound_rune=int(j.get('pending_inbound_rune', 0)),
            pending_inbound_asset=int(j.get('pending_inbound_asset', 0)),
            savers_depth=int(j.get('savers_depth', 0)),
            savers_units=int(j.get('savers_units', 0)),
            synth_mint_paused=bool(j.get('synth_mint_paused', False)),
        )


class ThorConstants(NamedTuple):
    constants: dict = None
    data_types: dict = None

    DATA_TYPES = ('int_64_values', 'bool_values', 'string_values')

    @classmethod
    def from_json(cls, j):
        holder = cls({}, {})
        for dt in cls.DATA_TYPES:
            subset = j.get(dt, {})
            holder.data_types[dt] = {}
            for k, v in subset.items():
                holder.constants[k] = v
                holder.data_types[dt][k] = v

        return holder

    def get(self, name, default=None):
        return self.constants.get(name, default)

    def __getitem__(self, item):
        return self.constants[item]


class ThorMimir(NamedTuple):
    constants: dict = None

    @classmethod
    def from_json(cls, j: dict):
        holder = cls({})
        for k, v in j.items():
            holder.constants[k] = v
        return holder

    def get(self, name, default=None):
        return self.constants.get(name, default)

    def __getitem__(self, item):
        return self.constants[item]


class ThorChainInfo(NamedTuple):
    chain: str = ''
    pub_key: str = ''
    address: str = ''
    router: str = ''  # for smart-contract based chains
    halted: bool = False
    gas_rate: int = 0
    chain_lp_actions_paused: bool = False
    chain_trading_paused: bool = False
    dust_threshold: int = 0
    gas_rate_units: str = ''
    global_trading_paused: bool = False
    outbound_fee: int = 0
    outbound_tx_size: int = 0

    @property
    def is_ok(self):
        return self.chain and self.pub_key and self.address

    @classmethod
    def from_json(cls, j):
        return cls(
            chain=j.get('chain', ''),
            pub_key=j.get('pub_key', ''),
            address=j.get('address', ''),
            router=j.get('router', ''),
            halted=bool(j.get('halted', True)),
            gas_rate=int(j.get('gas_rate', 0)),
            chain_lp_actions_paused=bool(j.get('chain_lp_actions_paused', False)),
            chain_trading_paused=bool(j.get('chain_trading_paused', False)),
            global_trading_paused=bool(j.get('global_trading_paused', False)),
            dust_threshold=int(j.get('dust_threshold', 0)),
            gas_rate_units=j.get('gas_rate_units', ''),
            outbound_fee=int(j.get('outbound_fee', 0)),
            outbound_tx_size=int(j.get('outbound_tx_size', 0))
        )


class ThorCoin(NamedTuple):
    asset: str = ''
    amount: int = 0
    decimals: int = 18

    @classmethod
    def from_json(cls, j):
        return cls(
            asset=j.get('asset'),
            amount=int(j.get('amount', 0)),
            decimals=int(j.get('decimals', 18))
        )

    @property
    def amount_float(self):
        return self.amount / (10 ** self.decimals)

    @classmethod
    def from_json_bank(cls, j):
        return cls(
            amount=int(j.get('amount', 0)),
            asset=j.get('denom', ''),
            decimals=8
        )


class ThorRouter(NamedTuple):
    chain: str = ''
    router: str = ''

    @classmethod
    def from_json(cls, j):
        return cls(
            chain=j.get('chain', ''),
            router=j.get('router', '')
        )


class ThorAddress(NamedTuple):
    chain: str = ''
    address: str = ''

    @classmethod
    def from_json(cls, j):
        return cls(
            chain=j.get('chain', ''),
            address=j.get('address', '')
        )


class ThorVault(NamedTuple):
    block_height: int = 0
    pub_key: str = ''
    coins: List[ThorCoin] = None
    type: str = ''
    status: str = ''
    status_since: int = 0
    membership: List[str] = None
    chains: List[str] = None
    inbound_tx_count: int = 0
    outbound_tx_count: int = 0
    routers: List[ThorRouter] = None
    addresses: List[ThorAddress] = None

    TYPE_YGGDRASIL = 'YggdrasilVault'
    TYPE_ASGARD = 'AsgardVault'

    STATUS_ACTIVE = "Active"
    STATUS_ACTIVE_VAULT = "ActiveVault"
    STATUS_STANDBY = "Standby"
    STATUS_RETIRING = "RetiringVault"

    @property
    def is_active(self):
        return self.status in (self.STATUS_ACTIVE, self.STATUS_ACTIVE_VAULT)

    @classmethod
    def from_json(cls, j):
        return cls(
            block_height=int(j.get('block_height', 0)),
            pub_key=j.get('pub_key', ''),
            coins=[ThorCoin.from_json(coin) for coin in j.get('coins', [])],
            type=j.get('type', ''),
            status=j.get('status', ''),
            status_since=int(j.get('status_since', 0)),
            membership=j.get('membership', []),
            chains=j.get('chains', []),
            inbound_tx_count=int(j.get('inbound_tx_count', 0)),
            outbound_tx_count=int(j.get('outbound_tx_count', 0)),
            routers=[ThorRouter.from_json(r) for r in j.get('routers', [])],
            addresses=[ThorAddress.from_json(a) for a in j.get('addresses', [])],
        )


RUNE = 'rune'


class ThorBalances(NamedTuple):
    height: int
    assets: List[ThorCoin]
    address: str

    @property
    def runes(self):
        for asset in self.assets:
            if asset.asset == RUNE:
                return asset.amount
        return 0

    @property
    def runes_float(self):
        return thor_to_float(self.runes)

    @classmethod
    def from_json(cls, j, address):
        return cls(
            height=0,
            assets=[
                ThorCoin.from_json_bank(item) for item in j.get('balances')
            ],
            address=address
        )

    def find_by_name(self, name):
        candidates = [coin for coin in self.assets if coin.asset == name]
        return candidates[0] if candidates else None


class ThorBlock(NamedTuple):
    height: int
    chain_id: str
    time: datetime.datetime
    hash: str
    txs_hashes: List[str]

    @classmethod
    def decode_tx_hash(cls, tx_b64: str):
        decoded = base64.b64decode(tx_b64.encode('utf-8'))
        return sha256(decoded).hexdigest().upper()

    @classmethod
    def from_json(cls, j):
        result = j.get('result', {})
        block = result['block']
        header = block['header']
        time = date_parser(header['time'])

        txs = [
            '0x' + cls.decode_tx_hash(content) for content in block['data']['txs']
        ]

        return cls(
            height=int(header['height']),
            chain_id=header['chain_id'],
            time=time,
            hash=result['block_id']['hash'],
            txs_hashes=txs
        )


class ThorTxAttribute(NamedTuple):
    key: str
    value: str
    index: bool

    @classmethod
    def from_json(cls, j):
        k = j.get('key')
        v = j.get('value')
        return cls(
            base64.b64decode(k).decode('utf-8') if k else None,
            base64.b64decode(v).decode('utf-8') if v else None,
            bool(j['index'])
        )


class ThorTxEvent(NamedTuple):
    type: str
    attributes: List[ThorTxAttribute]

    @classmethod
    def from_json(cls, j):
        return cls(
            type=j['type'],
            attributes=[ThorTxAttribute.from_json(a) for a in j['attributes']]
        )

    def value_of(self, key):
        return next(a.value for a in self.attributes if a.key == key)

    @property
    def sender(self):
        return self.value_of('sender')

    @property
    def recipient(self):
        return self.value_of('recipient')

    @property
    def amount(self):
        amt_str = self.value_of('amount')
        value, asset = re.findall(r'[A-Za-z]+|\d+', amt_str)
        return int(value), asset


class ThorNativeTX(NamedTuple):
    hash: str
    height: int
    index: int
    code: int
    data: str
    log: List[dict]
    gas_wanted: int
    gas_used: int
    events: List[ThorTxEvent]

    TYPE_SET_MIMIR = 'set_mimir_attr'
    TYPE_ADD_LIQUIDITY = 'add_liquidity'
    TYPE_WITHDRAW = 'withdraw'

    @property
    def type(self):
        return re.sub(r'[^a-zA-Z0-9_]', '', self.data)

    @property
    def transfers(self):
        return [e for e in self.events if e.type == 'transfer']

    @classmethod
    def from_json(cls, j):
        result = j.get('result', j)
        tx_result = result['tx_result']
        data = base64.b64decode(tx_result['data']).decode('utf-8').strip()
        log = ujson.loads(tx_result['log'])
        events = [ThorTxEvent.from_json(e) for e in tx_result['events']]

        return cls(
            hash=result['hash'],
            height=int(result['height']),
            index=int(result['index']),
            code=int(tx_result['code']),
            data=data,
            log=log,
            gas_wanted=int(tx_result['gas_wanted']),
            gas_used=int(tx_result['gas_used']),
            events=events
        )


class ThorLiquidityProvider(NamedTuple):
    asset: str
    asset_address: str
    rune_address: str
    last_add_height: int
    last_withdraw_height: int
    units: int
    pending_rune: int
    pending_asset: int
    pending_tx_id: str
    rune_deposit_value: int
    asset_deposit_value: int

    @classmethod
    def from_json(cls, j):
        return cls(
            asset=j.get('asset'),
            asset_address=j.get('asset_address'),
            rune_address=j.get('rune_address'),
            last_add_height=int(j.get('last_add_height', 0)),
            last_withdraw_height=int(j.get('last_withdraw_height', 0)),
            units=int(j.get('units', 0)),
            pending_rune=int(j.get('pending_rune', 0)),
            pending_asset=int(j.get('pending_asset', 0)),
            rune_deposit_value=int(j.get('rune_deposit_value', 0)),
            asset_deposit_value=int(j.get('asset_deposit_value', 0)),
            pending_tx_id=j.get('pending_tx_id') or j.get('pending_tx_Id'),  # id vs Id (both possible)
        )


class ThorMimirVote(NamedTuple):
    key: str
    value: int
    singer: str

    @classmethod
    def from_json(cls, j):
        return cls(
            key=j.get('key', ''),
            value=int(j.get('value', 0)),
            singer=j.get('signer', '')
        )

    @classmethod
    def from_json_array(cls, j):
        return [cls.from_json(item) for item in j] if j else []


class ThorPOL(NamedTuple):
    current_deposit: int  # current amount of rune deposited
    pnl: int  # total value of protocol's LP position in RUNE value
    rune_deposited: int  # total amount of RUNE withdrawn from the pools
    rune_withdrawn: int  # total amount of RUNE deposited into the pools
    value: int  # total value of protocol's LP position in RUNE value

    @classmethod
    def from_json(cls, j):
        return cls(
            current_deposit=int(j.get('current_deposit'), 0),
            pnl=int(j.get('pnl', 0)),
            rune_deposited=int(j.get('rune_deposited', 0)),
            rune_withdrawn=int(j.get('rune_withdrawn', 0)),
            value=int(j.get('value', 0)),
        )


class ThorNetwork(NamedTuple):
    bond_reward_rune: int
    burned_bep_2_rune: int
    burned_erc_20_rune: int
    total_bond_units: int
    total_reserve: int
    vaults_migrating: bool

    @classmethod
    def from_json(cls, j):
        return cls(
            bond_reward_rune=int(j.get('bond_reward_rune'), 0),
            burned_bep_2_rune=int(j.get('burned_bep_2_rune', 0)),
            burned_erc_20_rune=int(j.get('burned_erc_20_rune', 0)),
            total_bond_units=int(j.get('total_bond_units', 0)),
            total_reserve=int(j.get('total_reserve', 0)),
            vaults_migrating=bool(j.get('vaults_migrating', False)),
        )


class ThorSwapperClout(NamedTuple):
    address: str
    score: int
    reclaimed: int
    spent: int
    last_spent_height: int

    @classmethod
    def from_json(cls, j):
        return cls(
            address=j.get('address', ''),
            score=int(j.get('score', 0)),
            reclaimed=int(j.get('reclaimed', 0)),
            spent=int(j.get('spent', 0)),
            last_spent_height=int(j.get('last_spent_height', 0)),
        )
