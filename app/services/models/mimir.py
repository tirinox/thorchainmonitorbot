import logging
import math
import operator
import typing
from dataclasses import dataclass
from itertools import chain

from aiothornode.types import ThorConstants, ThorMimir

from services.lib.texts import split_by_camel_case
from services.models.base import BaseModelMixin
from services.models.mimir_naming import TRANSLATE_MIMIRS, EXCLUDED_VOTE_KEYS, MimirUnits
from services.models.node_info import NodeInfo

# for automatic Mimir, when it becomes 0 -> 1 or 1 -> 0, that is Admin's actions
ADMIN_VALUE = 1


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

        min_votes_to_pass = self.min_votes_to_pass
        for opt in options:
            opt.progress = len(opt.signers) / self.active_nodes
            opt.need_votes_to_pass = abs(min_votes_to_pass - opt.number_votes)
        self.top_options = options

    @property
    def min_votes_to_pass(self):
        return int(math.ceil(self.active_nodes * self.SUPER_MAJORITY))

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
    def __init__(self, all_votes: typing.List[MimirVote], active_nodes: typing.List[NodeInfo], exclude_keys):
        active_signers = [n.node_address for n in active_nodes if n.node_address and n.is_active]
        active_votes = [vote for vote in all_votes if vote.singer in active_signers]

        self.votes = active_votes
        self.active_node_count = len(active_nodes)

        self.all_voting = {}
        for vote in active_votes:
            if vote.key in exclude_keys:
                continue
            if vote.key not in self.all_voting:
                self.all_voting[vote.key] = MimirVoting(vote.key, {}, self.active_node_count, [])
            voting = self.all_voting.get(vote.key)
            if voting:
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

    @staticmethod
    def can_be_automatic(name: str):
        name = name.strip().upper()
        is_halt = name.startswith('HALT') or name.startswith('SOLVENCYHALT')
        return is_halt or name in MimirHolder.EXTRA_AUTO_SOLVENCY_MIMIRS

    @property
    def automated(self):
        return self.can_be_automatic(self.name)


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
        if self.kind == self.VALUE_CHANGE and self.is_automatic:
            logging.info(f'Mimir {self.name} became automatic. Change: {self}')
            self.entry.source = MimirEntry.SOURCE_AUTO

    @property
    def is_automatic(self):
        o, n = int(self.old_value), int(self.new_value)
        is_admin = (o == ADMIN_VALUE and n == 0) or (o == 0 and n == ADMIN_VALUE)
        return self.entry.automated and not is_admin
    

class MimirHolder:
    def __init__(self) -> None:
        self.last_changes: typing.Dict[str, float] = {}

        self._const_map = {}
        self._all_names = set()
        self._mimir_only_names = set()
        self.node_mimir = {}
        self.voting_manager = MimirVoteManager([], [], [])
        self.hard_coded_pretty_names = {}

    EXTRA_AUTO_SOLVENCY_MIMIRS = [
        'STOPFUNDYGGDRASIL'
    ]

    @staticmethod
    def detect_auto_solvency_checker(name: str, value):
        return MimirEntry.can_be_automatic(name) and (value != ADMIN_VALUE and value != 0)

    def get_constant(self, name: str, default=0, const_type: typing.Optional[type] = int):
        entry = self.get_entry(name)
        return const_type(entry.real_value) if entry else default

    def get_hardcoded_const(self, name: str, default=None):
        entry = self.get_entry(name)
        return entry.hard_coded_value if entry else default

    def get_entry(self, name) -> typing.Optional[MimirEntry]:
        return self._const_map.get(name.upper())

    def pretty_name(self, name):
        return TRANSLATE_MIMIRS.get(name) or self.hard_coded_pretty_names.get(name) or name

    def update(self, constants: ThorConstants, mimir: ThorMimir, node_mimir, node_votes: typing.List[MimirVote],
               active_nodes: typing.List[NodeInfo]):

        self.voting_manager = MimirVoteManager(node_votes, active_nodes, EXCLUDED_VOTE_KEYS)

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
            elif name in overridden_names or name not in const_names:
                source = MimirEntry.SOURCE_ADMIN
            else:
                source = MimirEntry.SOURCE_CONST

            hard_coded_value = hard_coded_constants.get(name)
            last_change_ts = self.last_changes.get(name, 0)
            units = MimirUnits.get_mimir_units(name)

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
