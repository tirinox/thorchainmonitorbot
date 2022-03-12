import math
import operator
import typing
from dataclasses import dataclass
from itertools import chain

from aiothornode.types import ThorConstants, ThorMimir

from services.lib.texts import split_by_camel_case
from services.models.base import BaseModelMixin


@dataclass
class MimirVote:
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


@dataclass
class MimirVoteOption:
    value: int
    signers: list
    progress: float = 0.0
    need_votes_to_pass: int = 0

    @property
    def number_votes(self):
        return len(self.signers)


@dataclass
class MimirVoting:
    key: str
    options: typing.Dict[int, MimirVoteOption]
    active_nodes: int
    top_options: typing.List[MimirVoteOption]

    SUPER_MAJORITY = 0.66666667

    def finalize_calculations(self):
        options = list(self.options.values())
        options.sort(key=operator.attrgetter('number_votes'), reverse=True)

        if not self.active_nodes:
            self.active_nodes = 1  # Just to avoid division by zero

        min_votes_to_pass = int(math.ceil(self.active_nodes * self.SUPER_MAJORITY))
        for opt in options:
            opt.progress = len(opt.signers) / self.active_nodes
            opt.need_votes_to_pass = abs(min_votes_to_pass - opt.number_votes)
        self.top_options = options

    @property
    def total_voters(self):
        if not self.options:
            return 0
        return sum(len(opt.signers) for opt in self.options.values())

    @property
    def passed(self):
        if not self.top_options:
            return False
        return self.top_options[0].progress >= self.SUPER_MAJORITY


class MimirVoteManager:
    def __init__(self, votes: typing.List[MimirVote], active_node_count: int, exclude_keys):
        self.votes = votes
        self.active_node_count = active_node_count

        self.all_voting = {}
        for vote in votes:
            if vote.key in exclude_keys:
                continue
            if vote.key not in self.all_voting:
                self.all_voting[vote.key] = MimirVoting(vote.key, {}, active_node_count, [])
            voting = self.all_voting[vote.key]

            if vote.value not in voting.options:
                voting.options[vote.value] = MimirVoteOption(vote.value, [])
            voting.options[vote.value].signers.append(vote.singer)

        for voting in self.all_voting.values():
            voting.finalize_calculations()

    @property
    def all_voting_list(self) -> typing.List[MimirVoting]:
        return list(self.all_voting.values())


@dataclass
class MimirEntry:
    name: str
    pretty_name: str
    real_value: str
    hard_coded_value: str
    changed_ts: int
    units: str
    source: str

    UNITS_RUNES = 'runes'
    UNITS_BLOCKS = 'blocks'
    UNITS_BOOL = 'bool'

    SOURCE_CONST = 'const'
    SOURCE_ADMIN = 'admin'
    SOURCE_AUTO = 'auto'
    SOURCE_NODE = 'node-mimir'
    SOURCE_NODE_CEASED = 'node-mimir-ceased'

    @property
    def automatic(self) -> bool:
        return self.source == self.SOURCE_AUTO

    @property
    def hardcoded(self) -> bool:
        return self.hard_coded_value is not None


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
        self.last_changes: typing.Dict[str, float] = {}

        self._const_map = {}
        self._all_names = set()
        self._mimir_only_names = set()
        self.node_mimir = {}
        self.node_mimir_votes = []
        self.voting_manager = MimirVoteManager([], 1, [])
        self.hard_coded_pretty_names = {}

    BLOCK_CONSTANTS = {
        name.upper() for name in [
            'BlocksPerYear', 'FundMigrationInterval', 'ChurnInterval', 'ChurnRetryInterval',
            'SigningTransactionPeriod', 'DoubleSignMaxAge', 'LiquidityLockUpBlocks',
            'ObservationDelayFlexibility', 'YggFundRetry', 'JailTimeKeygen', 'JailTimeKeysign',
            'NodePauseChainBlocks', 'FullImpLossProtectionBlocks', 'TxOutDelayMax', 'MaxTxOutOffset',
        ]
    }

    EXCLUDED_VOTE_KEYS = ['TEST']

    RUNE_CONSTANTS = {
        name.upper() for name in [
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
            'PoolDepthForYggFundingMin',
        ]
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
        'HALTDOGECHAIN',
        'HALTDOGETRADING',
        "HALTTRADING",
        "MINTSYNTHS",
        "PAUSELP",
        "PAUSELPBCH",
        "PAUSELPBNB",
        "PAUSELPBTC",
        "PAUSELPETH",
        "PAUSELPLTC",
        "PAUSELPDOGE",
        "STOPFUNDYGGDRASIL",
        "STOPSOLVENCYCHECK",
        "THORNAME",
        "THORNAMES",
        'STOPSOLVENCYCHECKETH',
        'STOPSOLVENCYCHECKBNB',
        'STOPSOLVENCYCHECKLTC',
        'STOPSOLVENCYCHECKBTC',
        'STOPSOLVENCYCHECKBCH',
        'STOPSOLVENCYCHECKDOGE',
        'STRICTBONDLIQUIDITYRATIO',
    }

    TRANSLATE_MIMIRS = {
        'PAUSELPLTC': 'Pause LP LTC',
        'PAUSELPETH': 'Pause LP ETH',
        'PAUSELPBCH': 'Pause LP BCH',
        'PAUSELPBNB': 'Pause LP BNB',
        'PAUSELPBTC': 'Pause LP BTC',
        'PAUSELPDOGE': 'Pause LP Doge',
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

        'HALTDOGECHAIN': 'Halt DOGE Chain',
        'HALTDOGETRADING': 'Halt DOGE Trading',

        'HALTTHORCHAIN': 'Halt ThorChain',
        'HALTTRADING': 'Halt All Trading',

        'MAXIMUMLIQUIDITYRUNE': 'Maximum Liquidity Rune',
        'MAXLIQUIDITYRUNE': 'Max Liquidity Rune',

        'MAXUTXOSTOSPEND': 'Max UTXO to Spend',

        'THORNAME': 'THOR Name',
        'THORNAMES': 'THOR Names',

        'STOPSOLVENCYCHECKETH': 'Stop Solvency check ETH',
        'STOPSOLVENCYCHECKBNB': 'Stop Solvency check BNB',
        'STOPSOLVENCYCHECKLTC': 'Stop Solvency check LTC',
        'STOPSOLVENCYCHECKBTC': 'Stop Solvency check BTC',
        'STOPSOLVENCYCHECKBCH': 'Stop Solvency check BCH',
        'STOPSOLVENCYCHECKDOGE': 'Stop Solvency check DOGE',
        'STRICTBONDLIQUIDITYRATIO': 'Strict Bond Liquidity Ratio',

        'POOLDEPTHFORYGGFUNDINGMIN': 'Pool Depth For Ygg Funding Min',

        'MAXSYNTHASSETDEPTH': 'Max Synth Asset Depth',
    }

    @staticmethod
    def detect_auto_solvency_checker(name: str, value):
        name = name.upper()
        if name.startswith('HALT') and (name.endswith('CHAIN') or name.endswith('TRADING')):
            if int(value) > 2:
                return True
        return False

    def get_constant(self, name: str, default=0, const_type: typing.Optional[type] = int):
        entry = self.get_entry(name)
        return const_type(entry.real_value) if entry else default

    def get_hardcoded_const(self, name: str, default=None):
        entry = self.get_entry(name)
        return entry.hard_coded_value if entry else default

    def get_entry(self, name) -> typing.Optional[MimirEntry]:
        return self._const_map.get(name.upper())

    def pretty_name(self, name):
        return self.TRANSLATE_MIMIRS.get(name) or self.hard_coded_pretty_names.get(name) or name

    def update(self, constants: ThorConstants, mimir: ThorMimir, node_mimir, node_votes: typing.List[MimirVote],
               number_of_active_nodes: int):
        self.voting_manager = MimirVoteManager(node_votes, number_of_active_nodes, self.EXCLUDED_VOTE_KEYS)

        hard_coded_constants = {n.upper(): v for n, v in constants.constants.items()}
        self.hard_coded_pretty_names = {
            n.upper(): split_by_camel_case(n)
            for n in constants.constants.keys()
        }
        mimir_constants = {n.upper(): v for n, v in mimir.constants.items()}
        node_mimir = {n.upper(): v for n, v in node_mimir.items()}

        const_names = set(hard_coded_constants.keys())
        mimir_names = set(mimir_constants.keys())
        node_mimir_names = set(node_mimir.keys())

        if node_mimir is not None:
            self.node_mimir = node_mimir
        if node_votes is not None:
            self.node_mimir_votes = node_votes

        self._mimir_only_names = mimir_names - const_names

        overridden_names = mimir_names & const_names
        self._all_names = mimir_names | const_names | node_mimir_names

        self._const_map = {}
        for name, current_value in chain(hard_coded_constants.items(), mimir_constants.items(), node_mimir.items()):
            is_automatic = self.detect_auto_solvency_checker(name, current_value)

            if is_automatic:
                source = MimirEntry.SOURCE_AUTO
            elif name in node_mimir_names:
                source = MimirEntry.SOURCE_NODE
            elif name in overridden_names:
                source = MimirEntry.SOURCE_ADMIN
            else:
                source = MimirEntry.SOURCE_CONST

            hard_coded_value = hard_coded_constants.get(name)
            last_change_ts = self.last_changes.get(name, 0)

            if name in self.RUNE_CONSTANTS:
                units = MimirEntry.UNITS_RUNES
            elif name in self.BLOCK_CONSTANTS:
                units = MimirEntry.UNITS_BLOCKS
            elif name in self.BOOL_CONSTANTS:
                units = MimirEntry.UNITS_BOOL
            else:
                units = ''

            self._const_map[name] = MimirEntry(
                name,
                self.pretty_name(name),
                current_value, hard_coded_value, last_change_ts,
                units=units,
                source=source
            )

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
