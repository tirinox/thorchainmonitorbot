"""
See: https://dev.thorchain.org/thorchain-dev/concepts/memos
"""
from dataclasses import dataclass
from enum import Enum
from typing import Union, NamedTuple, Optional, List

from lib.constants import THOR_BASIS_POINT_MAX

MAX_AFF_LEVELS = 5
THOR_AFFILIATE_BASIS_POINT_MAX = 1000


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

    # Prospective
    LIMIT_ORDER = 'limit_order'

    # RunePool
    RUNEPOOL_ADD = 'pool+'
    RUNEPOOL_WITHDRAW = 'pool-'

    # Outbounds
    REFUND = 'refund'
    OUTBOUND = 'out'

    # Special/dev-centric
    RESERVE = 'reserve'
    NOOP = 'noop'

    TRADE_ACC_DEPOSIT = 'trade+'
    TRADE_ACC_WITHDRAW = 'trade-'

    UNKNOWN = '_unknown_'


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


AUTO_OPTIMIZED = 0


class Affiliate(NamedTuple):
    address: str
    fee_bp: int


@dataclass
class THORMemo:
    action: ActionType
    asset: str = ''
    dest_address: str = ''
    limit: int = 0
    s_swap_interval: int = 0
    s_swap_quantity: int = 0  # 0 = optimized, 1 = single, >1 = streaming, None = don't care
    affiliates: list[Affiliate] = None
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
    chain: str = 'THOR'
    affiliate_asset: str = ''
    name_expiry: Union[str, int] = ''

    def __str__(self):
        return self.build()

    @property
    def affiliate_address(self) -> str:
        """
        Returns affiliate address/THORName when there is only one affiliate
        Returns '' if no affiliates
        Raises ValueError if multiple affiliates
        :return: Affiliate address/name
        """
        if not self.affiliates:
            return ''
        elif len(self.affiliates) == 1:
            return self.affiliates[0].address
        else:
            raise '/'.join(af.address for af in self.affiliates)

    @property
    def affiliate_fee_bp(self) -> int:
        """
        Returns affiliate fee in basis points (0...1000) when there is only one affiliate
        Returns 0 if no affiliates
        Raises ValueError if multiple affiliates
        :return: Affiliate fee in basis points
        """
        if not self.affiliates:
            return 0
        elif len(self.affiliates) == 1:
            return self.affiliates[0].fee_bp
        else:
            raise sum(af.fee_bp for af in self.affiliates)

    @property
    def has_affiliate_part(self):
        return bool(self.affiliates)

    @property
    def is_streaming(self):
        return self.s_swap_quantity > 1

    @property
    def uses_aggregator_out(self):
        return bool(self.dex_aggregator_address)

    @staticmethod
    def parse_dest_address(dest_address: str):
        if '/' in dest_address:
            dest_address, refund_address = dest_address.split('/', maxsplit=1)
        else:
            refund_address = dest_address
        return dest_address.strip(), refund_address.strip()

    @classmethod
    def parse_memo(cls, memo: str, no_raise=False):
        gist, *_comment = memo.split('|', maxsplit=2)  # ignore comments

        components = [it for it in gist.split(':')]

        ith = cls.ith_or_default

        action = ith(components, 0, '').lower()
        tx_type = MEMO_ACTION_TABLE.get(action)

        if tx_type == ActionType.ADD_LIQUIDITY:
            # ADD:POOL:PAIRED_ADDR:AFFILIATE:FEE
            # 0   1    2           3         4
            affiliates = cls._parse_affiliates(
                ith(components, 3, ''),
                ith(components, 4, ''),
            )
            return cls.add_liquidity(
                pool=ith(components, 1, ''),
                paired_address=ith(components, 2, ''),
                affiliates=affiliates,
            )

        elif tx_type == ActionType.SWAP:
            # 0    1     2         3   4         5   6                   7                8
            # SWAP:ASSET:DEST_ADDR:LIM:AFFILIATE:FEE:DEX Aggregator Addr:Final Asset Addr:MinAmountOut
            limit_and_s_swap = ith(components, 3, '')
            limit, s_swap_interval, s_swap_quantity = cls._parse_streaming_params(limit_and_s_swap)
            dest_address, refund_address = cls.parse_dest_address(ith(components, 2, ''))
            affiliates = cls._parse_affiliates(
                ith(components, 4, ''),
                ith(components, 5, ''),
            )
            return cls.swap(
                ith(components, 1),
                dest_address,  # 2
                limit, s_swap_interval, s_swap_quantity,  # 3
                affiliates=affiliates,
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
            affiliates = cls._parse_affiliates(
                ith(components, 4, ''),
                ith(components, 5, ''),
            )
            return cls.loan_open(
                asset=ith(components, 1),
                dest_address=ith(components, 2),
                limit=ith(components, 3, 0, is_number=True),
                affiliates=affiliates,
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
            return cls.deposit_trade_account(dest_address=ith(components, 1, ''))

        elif tx_type == ActionType.TRADE_ACC_WITHDRAW:
            return cls.withdraw_trade_account(dest_address=ith(components, 1, ''))

        elif tx_type == ActionType.RUNEPOOL_ADD:
            return cls.runepool_add()

        elif tx_type == ActionType.RUNEPOOL_WITHDRAW:
            affiliate = ith(components, 2, '')
            affiliate_fee_bp = ith(components, 3, 0)
            return cls.runepool_withdraw(
                bp=ith(components, 1, THOR_BASIS_POINT_MAX, is_number=True),
                affiliates=cls._parse_affiliates(affiliate, affiliate_fee_bp)
            )

        else:
            # todo: limit order, register memo, etc.
            if no_raise:
                return None
            else:
                raise NotImplementedError(f"Not able to parse memo for {action} yet")

    @property
    def _fee_or_empty(self):
        return str(self.affiliate_fee_bp) if self.affiliate_fee_bp is not None else ''

    def build(self):
        if self.action == ActionType.ADD_LIQUIDITY:
            # ADD:POOL:PAIRED_ADDR:AFFILIATE:FEE
            memo = f'+:{self.pool}:{self.dest_address}:{self._affiliate_part}'

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
                f':{self._affiliate_part}'
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
                f':{self._affiliate_part}'
            )

        elif self.action == ActionType.LOAN_CLOSE:
            # LOAN-:ASSET:DEST_ADDR:MIN_OUT
            memo = f'$-:{self.asset}:{self.dest_address}:{nothing_if_0(self.limit)}'

        elif self.action == ActionType.BOND:
            # # BOND:NODEADDR:PROVIDER:FEE
            if self.provider_address:
                memo = f'BOND:{self.node_address}:{self.provider_address}:{self._fee_or_empty}'
            else:
                memo = f'BOND:{self.node_address}'

        elif self.action == ActionType.UNBOND:
            # UNBOND:NODEADDR:AMOUNT:PROVIDER
            if self.provider_address:
                memo = f'UNBOND:{self.node_address}:{self.amount}:{self.provider_address}'
            else:
                memo = f'UNBOND:{self.node_address}:{self.amount}'

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
            memo = f'POOL-:{self.withdraw_portion_bp}:{self._affiliate_part}'

        else:
            raise NotImplementedError(f"Can not build memo for {self.action}")

        return memo.strip().rstrip(':')

    @classmethod
    def add_liquidity(cls, pool: str, paired_address: str = '',
                      affiliate_address: str = '', affiliate_fee_bp: int = 0,
                      affiliates: Optional[List[Affiliate]] = None):
        return cls(
            ActionType.ADD_LIQUIDITY, asset=pool, pool=pool,
            dest_address=paired_address,
            affiliates=cls._form_affiliates(affiliate_address, affiliate_fee_bp, affiliates)
        )

    @classmethod
    def add_savers(cls, pool: str, affiliate_address: str = '', affiliate_fee_bp: int = 0,
                   affiliates: Optional[List[Affiliate]] = None, ):
        assert '/' in pool, "Pool must be synth"
        return cls.add_liquidity(pool, '',
                                 affiliate_address=affiliate_address,
                                 affiliate_fee_bp=affiliate_fee_bp,
                                 affiliates=affiliates)

    @classmethod
    def swap(cls, asset: str, dest_address: str, limit: int = 0, s_swap_interval: int = 0,
             s_swap_quantity: int = None,
             affiliate_address: str = '', affiliate_fee_bp: int = 0,
             affiliates: Optional[List[Affiliate]] = None,
             dex_aggregator_address: str = '', dex_final_asset_address: str = '', dex_min_amount_out: int = 0,
             refund_address: str = ''):
        return cls(
            ActionType.SWAP,
            asset, dest_address, limit,
            s_swap_interval, s_swap_quantity,
            pool=asset,
            affiliates=cls._form_affiliates(affiliate_address, affiliate_fee_bp, affiliates),
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
        return cls.withdraw(pool, withdraw_portion_bp, asset='r')

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
                  affiliate_address: str = '', affiliate_fee_bp: int = 0,
                  affiliates: Optional[List[Affiliate]] = None
                  ):
        # LOAN+:BTC.BTC:bc1234567:minBTC:affAddr:affPts:dexAgg:dexTarAddr:DexTargetLimit
        # 0     1       2         3      4       5      6      7          8
        affiliates = affiliates or ([Affiliate(affiliate_address, affiliate_fee_bp)] if affiliate_address else [])
        return cls(
            ActionType.LOAN_OPEN,
            asset=asset,
            dest_address=dest_address,
            limit=limit,
            affiliates=affiliates,
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
            affiliates=[Affiliate(node_address, fee_bp)] if fee_bp else []
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
    def deposit_trade_account(cls, dest_address: str):
        return cls(
            ActionType.TRADE_ACC_DEPOSIT,
            dest_address=dest_address
        )

    @classmethod
    def withdraw_trade_account(cls, dest_address: str):
        return cls(
            ActionType.TRADE_ACC_WITHDRAW,
            dest_address=dest_address
        )

    @classmethod
    def runepool_add(cls):
        return cls(ActionType.RUNEPOOL_ADD)

    @classmethod
    def runepool_withdraw(cls, bp: int,
                          affiliate_address: str = '', affiliate_fee_bp: int = 0,
                          affiliates: Optional[List[Affiliate]] = None):
        return cls(
            ActionType.RUNEPOOL_WITHDRAW,
            withdraw_portion_bp=bp,
            affiliates=cls._form_affiliates(affiliate_address, affiliate_fee_bp, affiliates),
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
        s_swap_quantity = ith(s_swap_components, 2, is_number=True)
        return limit, s_swap_interval, s_swap_quantity

    @classmethod
    def _parse_affiliates(cls, names_part, fees_part):
        """
        Parses affiliate names and fees.
        :param names_part: A string like "10/20/0/40"
        :param fees_part: A string like "1/thor1/thor2/xyz"
        :return:
        """
        names = names_part.split('/')
        fees = fees_part.split('/') if fees_part.strip() else [0]
        n_fees, n_names = len(fees), len(names)
        if n_names != len(fees) and n_fees != 1:
            raise ValueError(f"Affiliates and fees mismatch: {names_part} vs {fees_part}")

        if n_fees == 1:
            # if there is only one fee, apply it to all affiliates
            fees = [int(fees[0])] * n_names
            n_fees = n_names

        fees = [(int(fee) if fee else 0) for fee in fees]
        for fee in fees:
            cls._guard_affiliate_bp(fee)

        if n_names > MAX_AFF_LEVELS or n_fees > MAX_AFF_LEVELS:
            raise ValueError(f"Too many affiliates: {names_part}:{fees_part}. Max {MAX_AFF_LEVELS}")

        return [Affiliate(name.strip(), fee) for name, fee in zip(names, fees) if name.strip()]

    @property
    def _affiliate_part(self):
        if not self.affiliates:
            return ':'
        if len(self.affiliates) > MAX_AFF_LEVELS:
            raise ValueError(f"Too many affiliates: {self.affiliates}. {MAX_AFF_LEVELS} max.")

        name_part = '/'.join(af.address.strip() for af in self.affiliates)

        fee_equal = all(af.fee_bp == self.affiliates[0].fee_bp for af in self.affiliates)
        fee_part = self.affiliates[0].fee_bp if fee_equal else '/'.join(str(af.fee_bp) for af in self.affiliates)
        return f'{name_part}:{fee_part}'

    @classmethod
    def _int_read(cls, x):
        x = str(x).lower()
        if 'e' in x:
            # e.g.: 232323e5
            return int(float(x))
        else:
            # just int
            return int(x)

    @classmethod
    def _guard_affiliate_bp(cls, affiliate_fee_bp):
        if affiliate_fee_bp < 0 or affiliate_fee_bp > THOR_AFFILIATE_BASIS_POINT_MAX:
            raise ValueError(
                f"Invalid affiliate fee: {affiliate_fee_bp}, must be in [0, {THOR_AFFILIATE_BASIS_POINT_MAX}]")

    @classmethod
    def _form_affiliates(cls,
                         affiliate_address: str = '', affiliate_fee_bp: int = 0,
                         affiliates: Optional[List[Affiliate]] = None) -> List[Affiliate]:
        if affiliates and (affiliate_address or affiliate_fee_bp):
            raise ValueError("Can not have both affiliates and affiliate_address/fee")

        if affiliates:
            if len(affiliates) > MAX_AFF_LEVELS:
                raise ValueError(f"Too many affiliates, max {MAX_AFF_LEVELS}")

            results = []
            for aff in affiliates:
                cls._guard_affiliate_bp(int(aff[1]))
                # we use indices to allow not only NamedTuple but also normal tuples
                results.append(Affiliate(aff[0].strip(), int(aff[1])))
            return results
        else:
            affiliate_fee_bp = int(affiliate_fee_bp)
            cls._guard_affiliate_bp(affiliate_fee_bp)
            return [Affiliate(affiliate_address, affiliate_fee_bp)] if affiliate_address else []
