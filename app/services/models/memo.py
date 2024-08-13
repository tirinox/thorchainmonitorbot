"""
Memo v2. This one is from xchainpy2 lib
See: https://dev.thorchain.org/thorchain-dev/concepts/memos
"""
from dataclasses import dataclass
from enum import Enum
from typing import Union

from services.lib.constants import THOR_BASIS_POINT_MAX

RUNE_TICKER = 'RUNE'


class ActionType(Enum):
    # Standard
    ADD_LIQUIDITY = 'addLiquidity'
    SWAP = 'swap'
    WITHDRAW = 'withdraw'
    DONATE = 'donate'

    # Name service
    THORNAME = 'thorname'

    # Lending
    LOAN_OPEN = 'loan+'
    LOAN_CLOSE = 'loan-'

    # Node operator/bond provider
    BOND = 'bond'
    UNBOND = 'unbond'
    LEAVE = 'leave'

    # Trade accounts
    TRADE_ACC_DEPOSIT = 'trade+'
    TRADE_ACC_WITHDRAW = 'trade-'

    # RunePool
    RUNEPOOL_ADD = 'pool+'
    RUNEPOOL_WITHDRAW = 'pool-'

    # Prospective
    LIMIT_ORDER = 'limit_order'

    # Outbounds
    REFUND = 'refund'
    OUTBOUND = 'out'

    # Special/dev-centric
    RESERVE = 'reserve'
    NOOP = 'noop'

    UNKNOWN = '_unknown_'
    NO_INTENT = 'no_intent'

    GROUP_ADD_WITHDRAW = (ADD_LIQUIDITY, WITHDRAW, DONATE)


def is_action(x, y):
    if isinstance(y, (tuple, set, list, dict)):
        return any(is_action(x, t) for t in y)

    if isinstance(x, ActionType):
        x = x.value
    if isinstance(y, ActionType):
        y = y.value

    return str(x).lower() == str(y).lower()


MEMO_ACTION_TABLE = {
    "add": ActionType.ADD_LIQUIDITY,
    "+": ActionType.ADD_LIQUIDITY,
    "withdraw": ActionType.WITHDRAW,
    "wd": ActionType.WITHDRAW,
    "-": ActionType.WITHDRAW,
    "swap": ActionType.SWAP,
    "s": ActionType.SWAP,
    "=": ActionType.SWAP,
    "limito": ActionType.LIMIT_ORDER,
    "lo": ActionType.LIMIT_ORDER,
    "out": ActionType.OUTBOUND,
    "donate": ActionType.DONATE,
    "d": ActionType.DONATE,
    "bond": ActionType.BOND,
    "unbond": ActionType.UNBOND,
    "leave": ActionType.LEAVE,
    "reserve": ActionType.RESERVE,
    "refund": ActionType.REFUND,
    "noop": ActionType.NOOP,
    "name": ActionType.THORNAME,
    "n": ActionType.THORNAME,
    "~": ActionType.THORNAME,
    "$+": ActionType.LOAN_OPEN,
    "loan+": ActionType.LOAN_OPEN,
    "$-": ActionType.LOAN_CLOSE,
    "loan-": ActionType.LOAN_CLOSE,
    "trade+": ActionType.TRADE_ACC_DEPOSIT,
    "trade-": ActionType.TRADE_ACC_WITHDRAW,
    "pool+": ActionType.RUNEPOOL_ADD,
    "pool-": ActionType.RUNEPOOL_WITHDRAW,
    # "migrate": TxMigrate,
    # "ragnarok": TxRagnarok,
    # "consolidate": TxConsolidate,
}


def nothing_if_0(x):
    return str(x) if x else ''


@dataclass
class THORMemo:
    action: ActionType
    asset: str = ''
    dest_address: str = ''
    limit: int = 0
    s_swap_interval: int = 0
    s_swap_quantity: int = 0  # 0 = optimized, 1 = single, >1 = streaming, None = don't care
    affiliate_address: str = ''
    affiliate_fee_bp: int = 0  # (0..10000) range, may be "node fee" as well in case of "Bond"
    dex_aggregator_address: str = ''
    final_asset_address: str = ''
    min_amount_out: int = 0
    tx_id: str = ''
    withdraw_portion_bp: int = 0
    pool: str = ''
    node_address: str = ''
    provider_address: str = ''
    amount: int = 0
    no_vault: bool = False
    refund_address: str = ''  # for swaps: dest_addr/refund_addr

    # THORName
    name: str = ''
    owner: str = ''
    chain: str = "THOR"
    affiliate_asset: str = ''
    name_expiry: Union[str, int] = ''

    def __str__(self):
        return self.build()

    @property
    def has_affiliate_part(self):
        return self.affiliate_address and self.affiliate_fee_bp > 0

    @property
    def is_streaming(self):
        return self.s_swap_quantity > 1

    @property
    def uses_aggregator_out(self):
        return bool(self.dex_aggregator_address)

    @property
    def affiliate_fee_0_1(self) -> float:
        return self.affiliate_fee_bp / THOR_BASIS_POINT_MAX

    @staticmethod
    def parse_dest_address(dest_address: str):
        if '/' in dest_address:
            dest_address, refund_address = dest_address.split('/', maxsplit=1)
        else:
            refund_address = dest_address
        return dest_address.strip(), refund_address.strip()

    @classmethod
    def parse_memo(cls, memo: str, no_raise=True):
        if memo.strip() == '':
            return cls(ActionType.NO_INTENT)

        gist, *_comment = memo.split('|', maxsplit=2)  # ignore comments

        components = [it for it in gist.split(':')]

        ith = cls.ith_or_default

        action = ith(components, 0, '').lower()
        tx_type = MEMO_ACTION_TABLE.get(action)

        if tx_type == ActionType.ADD_LIQUIDITY:
            # ADD:POOL:PAIRED_ADDR:AFFILIATE:FEE
            # 0   1    2           3         4
            return cls.add_liquidity(
                pool=ith(components, 1, ''),
                paired_address=ith(components, 2, ''),
                affiliate_address=ith(components, 3, ''),
                affiliate_fee_bp=ith(components, 4, 0, is_number=True),
            )

        elif tx_type == ActionType.SWAP:
            # 0    1     2         3   4         5   6                   7                8
            # SWAP:ASSET:DEST_ADDR:LIM:AFFILIATE:FEE:DEX Aggregator Addr:Final Asset Addr:MinAmountOut
            limit_and_s_swap = ith(components, 3, '')
            limit, s_swap_interval, s_swap_quantity = cls._parse_streaming_params(limit_and_s_swap)
            dest_address, refund_address = cls.parse_dest_address(ith(components, 2, ''))
            return cls.swap(
                ith(components, 1),
                dest_address,  # 2
                limit, s_swap_interval, s_swap_quantity,  # 3
                affiliate_address=ith(components, 4, ''),
                affiliate_fee_bp=ith(components, 5, 0, is_number=True),
                dex_aggregator_address=ith(components, 6, ''),
                dex_final_asset_address=ith(components, 7, ''),
                dex_min_amount_out=ith(components, 8, 0, is_number=True),
                refund_address=refund_address,  # /2
            )

        elif tx_type == ActionType.WITHDRAW:
            # WD:POOL:BASIS_POINTS:ASSET
            # 0  1    2            3
            return cls.withdraw(
                pool=ith(components, 1, ''),
                withdraw_portion_bp=ith(components, 2, THOR_BASIS_POINT_MAX, is_number=True),
                asset=ith(components, 3, ''),
            )

        elif tx_type == ActionType.THORNAME:
            # ~:name:chain:address:?owner:?preferredAsset:?expiry
            # 0 1    2     3       4      5               6
            return cls.thorname_register_or_renew(
                name=ith(components, 1),
                chain=ith(components, 2),
                address=ith(components, 3),
                thor_owner=ith(components, 4, ''),
                preferred_asset=ith(components, 5, ''),
                expiry=ith(components, 6, ''),
            )

        elif tx_type == ActionType.DONATE:
            return cls.donate(
                pool=ith(components, 1, '')
            )

        elif tx_type == ActionType.LOAN_OPEN:
            # LOAN+:BTC.BTC:bc1234567:minBTC:affAddr:affPts:dexAgg:dexTarAddr:DexTargetLimit
            # 0     1       2         3      4       5      6      7          8
            return cls.loan_open(
                asset=ith(components, 1),
                dest_address=ith(components, 2),
                limit=ith(components, 3, 0, is_number=True),
                affiliate_address=ith(components, 4, ''),
                affiliate_fee_bp=ith(components, 5, 0, is_number=True),
                # dex_aggregator_address=ith(components, 6, ''),
                # dex_final_asset_address=ith(components, 7, ''),
                # dex_min_amount_out=ith(components, 8, 0, is_number=True)
            )

        elif tx_type == ActionType.LOAN_CLOSE:
            # "LOAN-:BTC.BTC:bc1234567:minOut"
            #  0     1       2         3

            return cls.loan_close(
                asset=ith(components, 1),
                dest_address=ith(components, 2),
                min_out=ith(components, 3, 0, is_number=True)
            )

        elif tx_type == ActionType.BOND:
            # BOND:NODEADDR:PROVIDER:FEE
            # 0    1        2        3
            return cls.bond(
                node_address=ith(components, 1, ''),
                provider_address=ith(components, 2, ''),
                fee_bp=ith(components, 3, is_number=True),
            )

        elif tx_type == ActionType.UNBOND:
            # UNBOND:NODEADDR:AMOUNT:PROVIDER
            # 0      1        2      3
            return cls.unbond(
                node_address=ith(components, 1, ''),
                amount=ith(components, 2, 0, is_number=True),
                provider_address=ith(components, 3, ''),
            )

        elif tx_type == ActionType.LEAVE:
            # LEAVE:NODEADDR
            # 0     1
            return cls.leave(node_address=ith(components, 1, ''))

        elif tx_type == ActionType.OUTBOUND:
            return cls.outbound(tx_id=ith(components, 1, ''))

        elif tx_type == ActionType.REFUND:
            return cls.refund(tx_id=ith(components, 1, ''))

        elif tx_type == ActionType.RESERVE:
            return cls.reserve()

        elif tx_type == ActionType.NOOP:
            no_vault = ith(components, 1, default='').upper().strip() == 'NOVAULT'
            return cls.noop(no_vault)

        elif tx_type == ActionType.TRADE_ACC_DEPOSIT:
            return cls.trade_account_deposit(dest_address=ith(components, 1, ''))

        elif tx_type == ActionType.TRADE_ACC_WITHDRAW:
            return cls.trade_account_withdraw(dest_address=ith(components, 1, ''))

        elif tx_type == ActionType.RUNEPOOL_ADD:
            return cls.runepool_add()

        elif tx_type == ActionType.RUNEPOOL_WITHDRAW:
            return cls.runepool_withdraw(
                bp=ith(components, 1, THOR_BASIS_POINT_MAX, is_number=True),
                affiliate=ith(components, 2, ''),
                affiliate_fee_bp=ith(components, 3, 0, is_number=True)
            )

        else:
            # todo: limit order, register memo, etc.
            if no_raise:
                return None
            else:
                raise NotImplementedError(f"Not able to parse memo for {tx_type} yet")

    @property
    def _fee_or_empty(self):
        return str(self.affiliate_fee_bp) if self.affiliate_fee_bp is not None else ''

    def build(self):
        if self.action == ActionType.ADD_LIQUIDITY:
            # ADD:POOL:PAIRED_ADDR:AFFILIATE:FEE
            memo = f'+:{self.pool}:{self.dest_address}:{self.affiliate_address}:{nothing_if_0(self.affiliate_fee_bp)}'

        elif self.action == ActionType.SWAP:
            # 0    1     2         3   4         5   6                   7                8
            # SWAP:ASSET:DEST_ADDR:LIM:AFFILIATE:FEE:DEX Aggregator Addr:Final Asset Addr:MinAmountOut
            limit_or_ss = f'{nothing_if_0(self.limit)}'

            # for streaming swaps LIM is like LIM/INTERVAL/QUANTITY
            if self.s_swap_quantity is not None:
                limit_or_ss = f"{limit_or_ss}/{self.s_swap_interval}/{self.s_swap_quantity}"

            dest_addr = self.dest_address
            if self.refund_address and self.refund_address != dest_addr:
                dest_addr += f"/{self.refund_address}"

            memo = (
                f'=:{self.asset}:{dest_addr}:{limit_or_ss}'
                f':{self.affiliate_address}:{nothing_if_0(self.affiliate_fee_bp)}'
                f':{self.dex_aggregator_address}:{self.final_asset_address}:{nothing_if_0(self.min_amount_out)}'
            )

        elif self.action == ActionType.WITHDRAW:
            # -:POOL:BASIS_POINTS:ASSET
            # 0  1    2           3
            memo = f'-:{self.pool}:{nothing_if_0(self.withdraw_portion_bp)}:{self.asset}'

        elif self.action == ActionType.DONATE:
            memo = f'DONATE:{self.pool}'

        elif self.action == ActionType.THORNAME:
            # ~:name:chain:address:?owner:?preferredAsset:?expiry
            # 0 1    2     3       4      5               6
            expiry = self.name_expiry if self.name_expiry is not None else ''
            memo = (
                f'~:{self.name}:{self.chain}:{self.dest_address}:{self.owner}'
                f':{self.affiliate_asset}:{nothing_if_0(expiry)}'
            )

        elif self.action == ActionType.LOAN_OPEN:
            # LOAN+:ASSET:DESTADDR:MINOUT:AFFILIATE:FEE
            memo = (
                f'$+:{self.asset}:{self.dest_address}:{self.limit}'
                f':{self.affiliate_address}:{nothing_if_0(self.affiliate_fee_bp)}'
            )

        elif self.action == ActionType.LOAN_CLOSE:
            # LOAN-:ASSET:DEST_ADDR:MIN_OUT
            memo = f'$-:{self.asset}:{self.dest_address}:{nothing_if_0(self.limit)}'

        elif self.action == ActionType.BOND:
            # # BOND:NODEADDR:PROVIDER:FEE
            memo = f'BOND:{self.node_address}:{self.provider_address}:{self._fee_or_empty}'

        elif self.action == ActionType.UNBOND:
            # UNBOND:NODEADDR:AMOUNT:PROVIDER
            memo = f'UNBOND:{self.node_address}:{self.amount}:{self.provider_address}'

        elif self.action == ActionType.LEAVE:
            memo = f"LEAVE:{self.node_address}"

        elif self.action == ActionType.RESERVE:
            memo = 'RESERVE'

        elif self.action == ActionType.OUTBOUND:
            memo = f'OUT:{self.tx_id}'

        elif self.action == ActionType.REFUND:
            memo = f'REFUND:{self.tx_id}'

        elif self.action == ActionType.NOOP:
            memo = 'NOOP:NOVAULT' if self.no_vault else 'NOOP'

        elif self.action == ActionType.TRADE_ACC_DEPOSIT:
            memo = f'TRADE+:{self.dest_address}'

        elif self.action == ActionType.TRADE_ACC_WITHDRAW:
            memo = f'TRADE-:{self.dest_address}'

        elif self.action == ActionType.RUNEPOOL_ADD:
            memo = 'POOL+'

        elif self.action == ActionType.RUNEPOOL_WITHDRAW:
            memo = f'POOL-:{self.withdraw_portion_bp}:{self.affiliate_address}:{self.affiliate_fee_bp}'

        else:
            raise NotImplementedError(f"Can not build memo for {self.action}")

        return memo.strip().rstrip(':')

    @classmethod
    def add_liquidity(cls, pool: str, paired_address: str = '',
                      affiliate_address: str = '', affiliate_fee_bp: int = 0):
        return cls(
            ActionType.ADD_LIQUIDITY, asset=pool, pool=pool,
            dest_address=paired_address,
            affiliate_address=affiliate_address, affiliate_fee_bp=affiliate_fee_bp
        )

    @classmethod
    def add_savers(cls, pool: str, affiliate_address: str = '', affiliate_fee_bp: int = 0):
        assert '/' in pool, "Pool must be synth"
        return cls.add_liquidity(pool, affiliate_address=affiliate_address, affiliate_fee_bp=affiliate_fee_bp)

    @classmethod
    def swap(cls, asset: str, dest_address: str, limit: int = 0, s_swap_interval: int = 0,
             s_swap_quantity: int = None,
             affiliate_address: str = '', affiliate_fee_bp: int = 0,
             dex_aggregator_address: str = '', dex_final_asset_address: str = '', dex_min_amount_out: int = 0,
             refund_address: str = ''):
        return cls(
            ActionType.SWAP,
            asset, dest_address, limit,
            s_swap_interval, s_swap_quantity,
            pool=asset,
            affiliate_address=affiliate_address,
            affiliate_fee_bp=affiliate_fee_bp,
            dex_aggregator_address=dex_aggregator_address,
            final_asset_address=dex_final_asset_address,
            min_amount_out=dex_min_amount_out,
            refund_address=refund_address or dest_address,
        )

    @classmethod
    def withdraw(cls, pool: str, withdraw_portion_bp=THOR_BASIS_POINT_MAX, asset: str = ''):
        # WD:POOL:BASIS_POINTS:ASSET
        # 0  1    2           3
        return cls(
            ActionType.WITHDRAW, pool=pool, withdraw_portion_bp=withdraw_portion_bp, asset=asset
        )

    @classmethod
    def withdraw_savers(cls, pool: str, withdraw_portion_bp=THOR_BASIS_POINT_MAX):
        assert '/' in pool, "Pool must be synth"
        return cls.withdraw(pool, withdraw_portion_bp)

    @classmethod
    def withdraw_symmetric(cls, pool: str, withdraw_portion_bp=THOR_BASIS_POINT_MAX):
        return cls.withdraw(pool, withdraw_portion_bp)

    @classmethod
    def withdraw_rune(cls, pool: str, withdraw_portion_bp=THOR_BASIS_POINT_MAX):
        return cls.withdraw(pool, withdraw_portion_bp, asset=RUNE_TICKER)

    @classmethod
    def withdraw_asset(cls, pool: str, withdraw_portion_bp=THOR_BASIS_POINT_MAX):
        return cls.withdraw(pool, withdraw_portion_bp, asset=pool)

    @classmethod
    def donate(cls, pool: str):
        return cls(
            ActionType.DONATE,
            pool=pool, asset=pool
        )

    @classmethod
    def thorname_register_or_renew(cls, name: str, chain: str, address: str, thor_owner: str = '',
                                   preferred_asset: str = '',
                                   expiry=''):
        return cls(
            ActionType.THORNAME,
            name=name,
            chain=chain,
            dest_address=address,
            owner=thor_owner,
            name_expiry=expiry,
            affiliate_asset=preferred_asset,
        )

    @classmethod
    def loan_open(cls, asset: str, dest_address: str, limit: int = 0,
                  affiliate_address: str = '', affiliate_fee_bp: int = 0):
        # LOAN+:BTC.BTC:bc1234567:minBTC:affAddr:affPts:dexAgg:dexTarAddr:DexTargetLimit
        # 0     1       2         3      4       5      6      7          8
        return cls(
            ActionType.LOAN_OPEN,
            asset=asset,
            dest_address=dest_address,
            limit=limit,
            affiliate_address=affiliate_address,
            affiliate_fee_bp=affiliate_fee_bp,
            pool=asset,
        )

    @classmethod
    def loan_close(cls, asset: str, dest_address: str, min_out: int = 0):
        # "LOAN-:BTC.BTC:bc123456:minOut"
        #  0     1       2         3

        return cls(
            ActionType.LOAN_CLOSE,
            asset=asset, pool=asset,
            dest_address=dest_address, limit=min_out
        )

    @classmethod
    def bond(cls, node_address: str, provider_address: str = '', fee_bp: int = None):
        # BOND:NODEADDR:PROVIDER:FEE
        # 0    1        2        3
        return cls(
            ActionType.BOND,
            node_address=node_address,
            provider_address=provider_address,
            affiliate_fee_bp=fee_bp
        )

    @classmethod
    def unbond(cls, node_address: str, amount: int, provider_address: str = ''):
        # UNBOND:NODEADDR:AMOUNT:PROVIDER
        return cls(
            ActionType.UNBOND,
            node_address=node_address,
            provider_address=provider_address,
            amount=amount,
        )

    @classmethod
    def leave(cls, node_address: str):
        return cls(ActionType.LEAVE, node_address=node_address)

    @classmethod
    def limit_order(cls):
        raise NotImplementedError

    @classmethod
    def refund(cls, tx_id: str):
        return cls(ActionType.REFUND, tx_id=tx_id)

    @classmethod
    def outbound(cls, tx_id: str):
        return cls(ActionType.OUTBOUND, tx_id=tx_id)

    @classmethod
    def reserve(cls):
        # todo
        return cls(ActionType.RESERVE)

    @classmethod
    def noop(cls, no_vault=False):
        return cls(ActionType.NOOP, no_vault=no_vault)

    @classmethod
    def trade_account_deposit(cls, dest_address: str):
        return cls(
            ActionType.TRADE_ACC_DEPOSIT,
            dest_address=dest_address
        )

    @classmethod
    def trade_account_withdraw(cls, dest_address: str):
        return cls(
            ActionType.TRADE_ACC_WITHDRAW,
            dest_address=dest_address
        )

    @classmethod
    def runepool_add(cls):
        return cls(ActionType.RUNEPOOL_ADD)

    @classmethod
    def runepool_withdraw(cls, bp: int, affiliate: str = '', affiliate_fee_bp: int = 0):
        return cls(
            ActionType.RUNEPOOL_WITHDRAW,
            withdraw_portion_bp=bp,
            affiliate_address=affiliate,
            affiliate_fee_bp=affiliate_fee_bp,
        )

    # Utils:
    @classmethod
    def ith_or_default(cls, a, index, default=None, is_number=False) -> Union[str, int, float]:
        if 0 <= index < len(a):
            try:
                r = a[index].strip()
                if r == '':
                    return default
                return cls._int_read(r) if is_number else r
            except ValueError:
                return default
        else:
            return default

    @classmethod
    def _parse_streaming_params(cls, ss: str):
        s_swap_components = ss.split('/')

        ith = cls.ith_or_default
        limit = ith(s_swap_components, 0, 0, is_number=True)
        s_swap_interval = ith(s_swap_components, 1, 0, is_number=True)
        # 0 = optimized, 1 = single, >1 = streaming, None = don't care
        s_swap_quantity = ith(s_swap_components, 2, 1, is_number=True)
        return limit, s_swap_interval, s_swap_quantity

    @classmethod
    def _int_read(cls, x):
        x = str(x).lower()
        if 'e' in x:
            # e.g.: 232323e5
            return int(float(x))
        else:
            # just int
            return int(x)
