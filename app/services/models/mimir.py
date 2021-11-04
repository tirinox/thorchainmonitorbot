import typing
from dataclasses import dataclass

from aiothornode.types import ThorConstants, ThorMimir

from services.lib.texts import split_by_camel_case
from services.models.base import BaseModelMixin


@dataclass
class MimirChange(BaseModelMixin):
    kind: str
    name: str
    old_value: str
    new_value: str
    timestamp: float

    VALUE_CHANGE = '~'
    ADDED_MIMIR = '+'
    REMOVED_MIMIR = '-'

    def __post_init__(self):
        self.timestamp = float(self.timestamp)


class MimirEntry(typing.NamedTuple):
    name: str
    pretty_name: str
    real_value: str
    hard_coded_value: str
    overriden: bool
    changed_ts: int
    is_rune: bool
    is_blocks: bool


class MimirHolder:
    def __init__(self) -> None:
        self.last_constants: ThorConstants = ThorConstants()
        self.last_mimir: ThorMimir = ThorMimir()
        self.last_changes: typing.Dict[str, MimirChange] = {}

    MIMIR_PREFIX = 'mimir//'

    BLOCK_CONSTANTS = (
        'BlocksPerYear',
        'FundMigrationInterval',
        'ChurnInterval',
        'ChurnRetryInterval',
        'SigningTransactionPeriod',
        'DoubleSignMaxAge',
        'LiquidityLockUpBlocks',
        'ObservationDelayFlexibility',
        'YggFundRetry',
        'JailTimeKeygen',
        'JailTimeKeysign',
        'NodePauseChainBlocks',
        'FullImpLossProtectionBlocks',
        'TxOutDelayMax',
        'MaxTxOutOffset',
    )

    RUNE_CONSTANTS = (
        'OutboundTransactionFee',
        'NativeTransactionFee',
        'StagedPoolCost',
        'MinRunePoolDepth',
        'MinimumBondInRune',
        'MinTxOutVolumeThreshold',
        'TxOutDelayRate',
        'TNSFeePerBlock',
        'TNSRegisterFee'
    )

    @staticmethod
    def get_constant_static(name: str, mimir: ThorMimir, constants: ThorConstants,
                            default=0, const_type: typing.Optional[type] = int):
        raw_hardcoded_value = constants.constants.get(name, 0)
        hardcoded_value = const_type(raw_hardcoded_value) if const_type else raw_hardcoded_value

        prefix = MimirHolder.MIMIR_PREFIX
        mimir_name = f'{prefix}{name.upper()}'

        if mimir_name in mimir.constants:
            v = mimir.constants.get(mimir_name, default)
            return const_type(v) if const_type is not None else v
        else:
            return hardcoded_value

    @staticmethod
    def get_hardcoded_const_static(name: str, const_holder: ThorConstants, default=None):
        prefix = MimirHolder.MIMIR_PREFIX
        if name.startswith(prefix):
            pure_name = name[len(prefix):]
            for k, v in const_holder.constants.items():
                if pure_name.upper() == k.upper():
                    return v
            return default
        else:
            return const_holder.constants.get(name)

    def get_constant(self, name: str, default=0, const_type: typing.Optional[type] = int):
        return self.get_constant_static(name, self.last_mimir, self.last_constants, default=default,
                                        const_type=const_type)

    def get_hardcoded_const(self, name: str, default=None):
        return self.get_hardcoded_const_static(name, self.last_constants, default)

    def get_entry(self, const_name) -> MimirEntry:
        real_value = self.get_constant(const_name, const_type=None)
        hard_coded_value = self.get_hardcoded_const(const_name)
        overriden = real_value != hard_coded_value
        last_change = self.last_changes.get(const_name, None)
        ts = last_change.timestamp if last_change else 0
        return MimirEntry(const_name, split_by_camel_case(const_name),
                          real_value, hard_coded_value, overriden, ts,
                          is_rune=const_name in self.RUNE_CONSTANTS,
                          is_blocks=const_name in self.BLOCK_CONSTANTS)

    def update(self, constants: ThorConstants, mimir: ThorMimir):
        if constants:
            self.last_constants = constants
        if mimir:
            self.last_mimir = mimir
