import typing
from dataclasses import dataclass

from aiothornode.types import ThorConstants, ThorMimir

from services.lib.texts import split_by_camel_case
from services.models.base import BaseModelMixin


@dataclass
class MimirEntry:
    name: str
    pretty_name: str
    real_value: str
    hard_coded_value: str
    overridden: bool
    changed_ts: int
    is_rune: bool
    is_blocks: bool
    is_bool: bool
    source: str

    SOURCE_CONST = 'const'
    SOURCE_MIMIR = 'mimir'
    SOURCE_BOTH = 'both'


@dataclass
class MimirChange(BaseModelMixin):
    kind: str
    name: str
    old_value: str
    new_value: str
    entry: MimirEntry
    timestamp: float

    VALUE_CHANGE = '~'
    ADDED_MIMIR = '+'
    REMOVED_MIMIR = '-'

    def __post_init__(self):
        self.timestamp = float(self.timestamp)


class MimirHolder:
    def __init__(self) -> None:
        self.last_constants: ThorConstants = ThorConstants()
        self.last_mimir: ThorMimir = ThorMimir()

        self.last_changes: typing.Dict[str, float] = {}

        self._const_map = {}

        def mimirize(arr):
            return set([self.convert_name_to_mimir_key(n) for n in arr])

        self._mimir_names_of_block_constants = mimirize(self.BLOCK_CONSTANTS)
        self._mimir_names_of_rune_constants = mimirize(self.RUNE_CONSTANTS)
        self._mimir_names_of_bool_constants = mimirize(self.BOOL_CONSTANTS)

        self._all_names = set()
        self._mimir_only_names = set()

    MIMIR_PREFIX = 'mimir//'

    BLOCK_CONSTANTS = {
        'BlocksPerYear', 'FundMigrationInterval', 'ChurnInterval', 'ChurnRetryInterval',
        'SigningTransactionPeriod', 'DoubleSignMaxAge', 'LiquidityLockUpBlocks',
        'ObservationDelayFlexibility', 'YggFundRetry', 'JailTimeKeygen', 'JailTimeKeysign',
        'NodePauseChainBlocks', 'FullImpLossProtectionBlocks', 'TxOutDelayMax', 'MaxTxOutOffset'
    }

    RUNE_CONSTANTS = {
        'OutboundTransactionFee',
        'NativeTransactionFee',
        'StagedPoolCost',
        'MinRunePoolDepth',
        'MinimumBondInRune',
        'MinTxOutVolumeThreshold',
        'TxOutDelayRate',
        'TNSFeePerBlock',
        'TNSRegisterFee',
        'MAXIMUMLIQUIDITYRUNE',
        'MAXLIQUIDITYRUNE',
    }

    TRANSLATE_MIMIRS = {
        'PAUSELPLTC': 'Pause LP LTC',
        'PAUSELPETH': 'Pause LP ETH',
        'PAUSELPBCH': 'Pause LP BCH',
        'PAUSELPBNB': 'Pause LP BNB',
        'PAUSELPBTC': 'Pause LP BTC',
        'PAUSELP': 'Pause all LP',
        'STOPFUNDYGGDRASIL': 'Stop Fund Yggdrasil',
        'STOPSOLVENCYCHECK': 'Stol Solvency Check',
        'NUMBEROFNEWNODESPERCHURN': 'Number of New Nodes per Churn',
        'MINTSYNTHS': 'Mint Synths',
        'HALTBCHCHAIN': 'Halt BCH Chain',
        'HALTBCHTRADING': 'Halt BCH Trading',

        'HALTBNBCHAIN': 'Halt BNB Chain',
        'HALTBNBTRADING': 'Halt BNB Trading',

        'HALTBTCCHAIN': 'Halt BTC Chain',
        'HALTBTCTRADING': 'Halt BTC Trading',

        'HALTETHCHAIN': 'Halt ETH Chain',
        'HALTETHTRADING': 'Halt ETH Trading',

        'HALTLTCCHAIN': 'Halt LTC Chain',
        'HALTLTCTRADING': 'Halt LTC Trading',

        'HALTTHORCHAIN': 'Halt ThorChain',
        'HALTTRADING': 'Halt All Trading',

        'MAXIMUMLIQUIDITYRUNE': 'Maximum Liquidity Rune',
        'MAXLIQUIDITYRUNE': 'Max Liquidity Rune',

        'MAXUTXOSTOSPEND': 'Max UTXO to Spend',

        'THORNAME': 'THOR Name',
        'THORNAMES': 'THOR Names',
    }

    BOOL_CONSTANTS = {
        "HALTBCHCHAIN",
        "HALTBCHTRADING",
        "HALTBNBCHAIN",
        "HALTBNBTRADING",
        "HALTBTCCHAIN",
        "HALTBTCTRADING",
        "HALTETHCHAIN",
        "HALTETHTRADING",
        "HALTLTCCHAIN",
        "HALTLTCTRADING",
        "HALTTHORCHAIN",
        "HALTTRADING",
        "MINTSYNTHS",
        "PAUSELP",
        "PAUSELPBCH",
        "PAUSELPBNB",
        "PAUSELPBTC",
        "PAUSELPETH",
        "PAUSELPLTC",
        "STOPFUNDYGGDRASIL",
        "STOPSOLVENCYCHECK",
        "THORNAME",
        "THORNAMES",
    }

    @staticmethod
    def convert_name_to_mimir_key(name):
        prefix = MimirHolder.MIMIR_PREFIX
        if name.startswith(prefix):
            return name
        else:
            return f'{prefix}{name.upper()}'

    @staticmethod
    def pure_name(name: str):
        prefix = MimirHolder.MIMIR_PREFIX
        if name.startswith(prefix):
            return name[len(prefix):]
        else:
            return name.upper()

    def get_constant(self, name: str, default=0, const_type: typing.Optional[type] = int):
        raw_hardcoded_value = self.last_constants.constants.get(name, 0)
        hardcoded_value = const_type(raw_hardcoded_value) if const_type else raw_hardcoded_value

        mimir_name = MimirHolder.convert_name_to_mimir_key(name)

        if mimir_name in self.last_mimir.constants:
            v = self.last_mimir.constants.get(mimir_name, default)
            return const_type(v) if const_type is not None else v
        else:
            return hardcoded_value

    def get_hardcoded_const(self, name: str, default=None):
        prefix = MimirHolder.MIMIR_PREFIX
        if name.startswith(prefix):
            pure_name = name[len(prefix):]
            for k, v in self.last_constants.constants.items():
                if pure_name.upper() == k.upper():
                    return v
            return default
        else:
            return self.last_constants.constants.get(name)

    def get_entry(self, name) -> typing.Optional[MimirEntry]:
        return self._const_map.get(name)

    def update(self, constants: ThorConstants, mimir: ThorMimir):
        consts = set(constants.constants.keys())
        only_mimir_names = set()
        overriden_names = set()

        mimir_like_const_names = set(self.convert_name_to_mimir_key(n) for n in consts)
        for mimir_name in mimir.constants.keys():
            if mimir_name in mimir_like_const_names:
                overriden_names.add(mimir_name)
            else:
                only_mimir_names.add(mimir_name)

        self._const_map = {}
        self._all_names = set()
        self._mimir_only_names = set()

        for name, value in constants.constants.items():
            real_value = value
            overriden = False
            source = MimirEntry.SOURCE_CONST

            mimir_name = self.convert_name_to_mimir_key(name)
            if mimir_name in overriden_names:
                overriden = True
                source = MimirEntry.SOURCE_BOTH
                real_value = mimir.constants.get(mimir_name)

            last_change_ts = self.last_changes.get(name, 0)

            entry = MimirEntry(name, split_by_camel_case(name),
                               real_value, value, overriden, last_change_ts,
                               is_rune=name in self.RUNE_CONSTANTS,
                               is_blocks=name in self.BLOCK_CONSTANTS,
                               is_bool=name in self.BOOL_CONSTANTS,
                               source=source)
            self._const_map[name] = entry
            self._const_map[mimir_name] = entry
            self._all_names.add(name)

        for name in only_mimir_names:
            value = mimir.constants.get(name)

            last_change_ts = self.last_changes.get(name, 0)

            pure_name = self.pure_name(name)
            pretty_name = self.TRANSLATE_MIMIRS.get(pure_name, pure_name)

            entry = MimirEntry(name, pretty_name, value, value, True, last_change_ts,
                               is_rune=name in self._mimir_names_of_rune_constants,
                               is_blocks=name in self._mimir_names_of_block_constants,
                               is_bool=name in self._mimir_names_of_bool_constants,
                               source=MimirEntry.SOURCE_MIMIR)
            self._const_map[name] = entry
            self._const_map[pure_name] = entry
            self._all_names.add(name)
            self._mimir_only_names.add(name)

        if constants:
            self.last_constants = constants
        if mimir:
            self.last_mimir = mimir

    @property
    def all_entries(self) -> typing.List[MimirEntry]:
        entries = [self._const_map[name] for name in self._all_names]
        entries.sort(key=lambda en: en.pretty_name)
        return entries

    def register_change_ts(self, name, ts):
        if name:
            self.last_changes[name] = ts
            entry: MimirEntry = self._const_map.get(name)
            if entry and ts > 0:
                entry.changed_ts = ts
