import base64
import re
from typing import List, NamedTuple

import ujson

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
    synth_supply_remaining: int = 0

    loan_collateral_remaining: int = 0
    loan_collateral: int = 0
    loan_cr: int = 0
    derived_depth_bps: int = 0
    asset_tor_price: int = 0

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
            synth_supply_remaining=int(j.get('synth_supply_remaining', 0)),
            loan_collateral_remaining=int(j.get('loan_collateral_remaining', 0)),
            loan_collateral=int(j.get('loan_collateral', 0)),
            loan_cr=int(j.get('loan_cr', 0)),
            derived_depth_bps=int(j.get('derived_depth_bps', 0)),
            asset_tor_price=int(j.get('asset_tor_price', 0)),  # usd price of asset (TOR)
        )

    @property
    def tor_per_rune(self) -> float:
        return self.tor_per_asset * self.assets_per_rune

    @property
    def tor_per_asset(self) -> float:
        return thor_to_float(self.asset_tor_price)


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


class ThorTradeUnits(NamedTuple):
    asset: str
    units: int
    depth: int

    @classmethod
    def from_json(cls, j):
        return cls(
            asset=j.get('asset'),
            units=int(j.get('units', 0)),
            depth=int(j.get('depth', 0))
        )

    @property
    def depth_float(self):
        return thor_to_float(self.depth)

    @classmethod
    def from_json_array(cls, j):
        return [cls.from_json(item) for item in j] if j else []


class ThorTradeAccount(NamedTuple):
    asset: str
    units: int
    owner: str
    last_add_height: int
    last_withdraw_height: int
    usd_value: float = 0.0

    @classmethod
    def from_json(cls, j):
        return cls(
            asset=j.get('asset'),
            units=int(j.get('units', 0)),
            owner=j.get('owner', ''),
            last_add_height=int(j.get('last_add_height', 0)),
            last_withdraw_height=int(j.get('last_withdraw_height', 0))
        )

    @classmethod
    def from_json_array(cls, j):
        return [cls.from_json(item) for item in j] if j else []

    @property
    def value_float(self):
        return thor_to_float(self.units)

    def filled_usd_value(self, price_holder):
        if self.asset:
            usd_value = price_holder.convert_to_usd(self.value_float, self.asset)
            return self._replace(usd_value=usd_value)
        return self


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


class ThorTxStatus(NamedTuple):
    tx: dict
    planned_out_txs: List[dict]
    out_txs: List[dict]
    stages: dict

    @classmethod
    def from_json(cls, j):
        return cls(
            tx=j.get('tx'),
            planned_out_txs=j.get('planned_out_txs', []),
            out_txs=j.get('out_txs', []),
            stages=j.get('stages', {})
        )

    STAGE_SWAP_STATUS = 'swap_status'

    def get_stage(self, stage):
        return self.stages.get(stage, {})

    def get_streaming_swap(self):
        return self.get_stage(self.STAGE_SWAP_STATUS).get('streaming')


class ThorBorrowerPosition(NamedTuple):
    asset: str
    collateral_current: float
    collateral_deposited: float
    collateral_withdrawn: float
    debt_current: float
    debt_issued: float
    debt_repaid: float
    last_open_height: int
    last_repay_height: int
    owner: str

    @classmethod
    def from_json(cls, j):
        return cls(
            j['asset'],
            thor_to_float(j['collateral_current']),
            thor_to_float(j['collateral_deposited']),
            thor_to_float(j['collateral_withdrawn']),
            thor_to_float(j['debt_current']),
            thor_to_float(j['debt_issued']),
            thor_to_float(j['debt_repaid']),
            int(j['last_open_height']),
            int(j['last_repay_height']),
            j['owner']
        )


class ThorRunePoolPOL(NamedTuple):
    rune_deposited: int  # total amount of RUNE withdrawn from the pools
    rune_withdrawn: int  # total amount of RUNE withdrawn from the pools
    value: int  # total value of protocol's LP position in RUNE value
    pnl: int  # total value of protocol's LP position in RUNE value
    current_deposit: int  # current amount of rune deposited

    @classmethod
    def from_json(cls, j):
        return cls(
            rune_deposited=int(j.get('rune_deposited', 0)),
            rune_withdrawn=int(j.get('rune_withdrawn', 0)),
            value=int(j.get('value', 0)),
            pnl=int(j.get('pnl', 0)),
            current_deposit=int(j.get('current_deposit', 0)),
        )

    def to_dict(self):
        return {
            'rune_deposited': self.rune_deposited,
            'rune_withdrawn': self.rune_withdrawn,
            'value': self.value,
            'pnl': self.pnl,
            'current_deposit': self.current_deposit
        }

    @property
    def current_deposit_float(self):
        return thor_to_float(self.current_deposit)


class ThorRunePoolProviders(NamedTuple):
    units: int
    pending_units: int
    pending_rune: int
    value: int
    pnl: int
    current_deposit: int

    @classmethod
    def from_json(cls, j):
        return cls(
            units=int(j.get('units', 0)),
            pending_units=int(j.get('pending_units', 0)),
            pending_rune=int(j.get('pending_rune', 0)),
            value=int(j.get('value', 0)),
            pnl=int(j.get('pnl', 0)),
            current_deposit=int(j.get('current_deposit', 0)),
        )

    @property
    def current_deposit_float(self):
        return thor_to_float(self.current_deposit)

    def to_dict(self):
        return {
            'units': self.units,
            'pending_units': self.pending_units,
            'pending_rune': self.pending_rune,
            'value': self.value,
            'pnl': self.pnl,
            'current_deposit': self.current_deposit
        }


class ThorRunePoolReserve(NamedTuple):
    units: int
    value: int
    pnl: int
    current_deposit: int

    @classmethod
    def from_json(cls, j):
        return cls(
            units=int(j.get('units', 0)),
            value=int(j.get('value', 0)),
            pnl=int(j.get('pnl', 0)),
            current_deposit=int(j.get('current_deposit', 0)),
        )

    def to_dict(self):
        return {
            'units': self.units,
            'value': self.value,
            'pnl': self.pnl,
            'current_deposit': self.current_deposit
        }


class ThorRunePool(NamedTuple):
    pol: ThorRunePoolPOL
    providers: ThorRunePoolProviders
    reserve: ThorRunePoolReserve

    @classmethod
    def from_json(cls, j):
        return cls(
            pol=ThorRunePoolPOL.from_json(j.get('pol', {})),
            providers=ThorRunePoolProviders.from_json(j.get('providers', {})),
            reserve=ThorRunePoolReserve.from_json(j.get('reserve', {})),
        )

    def to_dict(self):
        return {
            'pol': self.pol.to_dict(),
            'providers': self.providers.to_dict(),
            'reserve': self.reserve.to_dict()
        }


class ThorRunePoolProvider(NamedTuple):
    rune_address: str
    units: int
    value: int
    pnl: int
    deposit_amount: int
    withdraw_amount: int
    last_deposit_height: int
    last_withdraw_height: int

    @property
    def rune_value(self):
        return thor_to_float(self.value)

    @classmethod
    def from_json(cls, j):
        return cls(
            rune_address=j.get('rune_address', ''),
            units=int(j.get('units', 0)),
            value=int(j.get('value', 0)),
            pnl=int(j.get('pnl', 0)),
            deposit_amount=int(j.get('deposit_amount', 0)),
            withdraw_amount=int(j.get('withdraw_amount', 0)),
            last_deposit_height=int(j.get('last_deposit_height', 0)),
            last_withdraw_height=int(j.get('last_withdraw_height', 0))
        )

    @classmethod
    def from_json_array(cls, j):
        return [cls.from_json(item) for item in j] if j else []
