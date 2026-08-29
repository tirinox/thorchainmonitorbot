import copy
import re

import wordninja
import yaml

from lib.path import get_data_path
from models.asset import Asset

MIMIR_KEY_KILL_SWITCH_START = 'KILLSWITCHSTART'
MIMIR_KEY_KILL_SWITCH_DURATION = 'KILLSWITCHDURATION'

MIMIR_KEY_MAX_SYNTH_PER_POOL_DEPTH = 'MAXSYNTHPERPOOLDEPTH'

MIMIR_KEY_MAX_RUNE_SUPPLY = 'MAXRUNESUPPLY'

MIMIR_KEY_SYSTEM_INCOME_BURN_RATE = 'SYSTEMINCOMEBURNRATEBPS'

# target synth per pool depth for POL (basis points)
MIMIR_KEY_POL_TARGET_SYNTH_PER_POOL_DEPTH = 'POLTARGETSYNTHPERPOOLDEPTH'
"""
if POLTargetSynthPerPoolDepth == 4500:
    POL will continue adding RUNE to a pool until the synth depth of that pool is 45%.
"""

# buffer around the POL synth utilization (basis points added to/subtracted from POLTargetSynthPerPoolDepth basis pts)
MIMIR_KEY_POL_BUFFER = "POLBUFFER"
"""
if POLBUFFER == 500:
    Synth utilization must be >5% from the target synth per pool depth in order to add liquidity / remove liquidity. 
    In this context, liquidity will be withdrawn below 40% synth utilization and deposited above 50% synth utilization.
"""

# Maximum amount of rune deposited into the pools
MIMIR_KEY_POL_MAX_NETWORK_DEPOSIT = "POLMAXNETWORKDEPOSIT"

# Maximum amount of rune to enter/exit a pool per iteration. This is in basis points of the pool rune depth
MIMIR_KEY_POL_MAX_POOL_MOVEMENT = "POLMAXPOOLMOVEMENT"
"""
if POLMaxPoolMovement == 1:
    POL will move the pool price at most 0.01% in one block
"""

MIMIR_KEY_POL_SYNTH_UTILIZATION = "POLSYNTHUTILIZATION"

SOL_RPC_PROVIDER_KEY = 'SOL-RPC-PROVIDER'

EXTRA_AUTO_SOLVENCY_MIMIRS = [
    'STOPFUNDYGGDRASIL'
]

MIMIR_PAUSE_GLOBAL = 'NODEPAUSECHAINGLOBAL'

MIMIR_ADVANCED_QUEUE_ENABLED = 'ENABLEADVSWAPQUEUE'

MIMIR_DICT_FILENAME = f'{get_data_path()}/mimir_naming.yaml'


class MimirUnits:
    UNITS_RUNES = 'runes'
    UNITS_BLOCKS = 'blocks'
    UNITS_UNTIL_BLOCK = 'until_block'
    UNITS_BOOL = 'bool'
    UNITS_VOTE_FOR_AGAINST = 'vote_for_against'
    UNITS_USD = 'usd'
    UNITS_BASIS_POINTS = 'basis_points'
    UNITS_INT = 'int'

    UNITS_SPECIAL_MAP = 'special_map'


class MimirNameRules:
    CUSTOM_WORD_COST = 8.0
    OPAQUE_IDENTIFIER_MIN_LENGTH = 16
    ASSET_KEY_PREFIXES = {
        'PAUSELPDEPOSIT': 'Pause LP Deposit',
        'POL': 'POL',
        'TORANCHOR': 'TOR Anchor',
    }

    def __init__(self):
        self.rules = {}
        self._canonical_names = {}
        self._canonical_word_transform = {}
        self._word_splitter = None

    def load(self, filename):
        self.rules = self._load_mimir_naming_rules(filename)
        self.make_words_proper()
        self.sort_word_transform()
        self._rebuild_word_splitter()

    @staticmethod
    def _split_camel_case(name: str):
        """Split a Go-style constant name while preserving acronyms and numbers."""
        return re.findall(
            r'[A-Z]+\d+|[A-Z]+s(?=[A-Z]|$)|'
            r'[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+',
            name,
        )

    def learn_canonical_names(self, names):
        """Learn exact titles and vocabulary from the case-preserving constants API."""
        parsed_names = []
        changed = False
        for name in names:
            if not isinstance(name, str) or not name:
                continue

            words = self._split_camel_case(name)
            if not words:
                continue
            parsed_names.append((name, words))

            for word in words:
                upper_word = word.upper()
                old_word = self._canonical_word_transform.get(upper_word)
                if old_word is None or (word.isupper() and not old_word.isupper()):
                    self._canonical_word_transform[upper_word] = word
                    changed = True

        for name, words in parsed_names:
            title = ' '.join(
                self._transform_each_word(word) for word in words
            )
            if self._canonical_names.get(name.upper()) != title:
                self._canonical_names[name.upper()] = title
                changed = True

        if changed:
            self._rebuild_word_splitter()

    def update_asset_names(self, assets):
        if isinstance(assets, dict):
            new_assets = set(assets.keys())
        elif isinstance(assets, (list, set, tuple)):
            new_assets = set(assets)
        else:
            return

        words_to_add = []
        for asset_name in new_assets:
            # in Mimir asset names appear without dots (ETH-AAVE-0X...)
            asset_pretty = Asset.from_string(asset_name).pretty_str

            asset_name_hyphen = asset_name.replace('.', '-')
            self.rules_word_transform[asset_name_hyphen] = asset_pretty
            words_to_add.append(asset_name_hyphen)
        self.add_words(words_to_add)

    @property
    def known_words(self):
        return self.rules.get('words', [])

    def save_to(self, filename):
        with open(filename, 'w') as f:
            yaml.safe_dump(self.rules, f)

    def add_words(self, words):
        self.rules['words'] += words
        self.make_words_proper()
        self._rebuild_word_splitter()

    def make_words_proper(self):
        # upper and strip
        words = [w.strip().upper() for w in self.known_words]
        # remove duplicates
        words = list(set(words))
        # sort by length longest first
        words = sorted(words, key=lambda w: (-len(w), w))
        # save
        self.rules['words'] = list(words)

    def sort_word_transform(self):
        transformed = {
            k.strip().upper(): v
            for k, v in self.rules_word_transform.items()
        }
        self.rules['word_transform'] = dict(sorted(transformed.items()))

    def _rebuild_word_splitter(self):
        # Copy the bundled offline English model so THORChain vocabulary can be
        # preferred without mutating wordninja's process-wide default model.
        splitter = copy.copy(wordninja.DEFAULT_LANGUAGE_MODEL)
        splitter._wordcost = dict(splitter._wordcost)

        custom_words = set(self.known_words) | set(self.rules_word_transform)
        custom_words |= set(self._canonical_word_transform)
        for word in custom_words:
            if not word.isalnum():
                continue
            normalized = word.lower()
            current_cost = splitter._wordcost.get(normalized, float('inf'))
            splitter._wordcost[normalized] = min(current_cost, self.CUSTOM_WORD_COST)

        if custom_words:
            splitter._maxword = max(
                splitter._maxword,
                max(map(len, custom_words)),
            )
        self._word_splitter = splitter

    @staticmethod
    def _load_mimir_naming_rules(filename):
        with open(filename, 'r') as f:
            data = yaml.safe_load(f)
        return data

    def get_special_voting_value_map(self, mimir_key):
        return self.rules.get('special_vote_values', {}).get(mimir_key, {})

    @property
    def rules_word_transform(self):
        return self.rules.get('word_transform', {})

    @property
    def excluded_from_voting(self):
        return self.rules.get('excluded_vote_keys', [])

    def _transform_each_word(self, word: str):
        up_word = word.upper()
        if up_word in self.rules_word_transform:
            word = self.rules_word_transform.get(up_word)
        elif up_word in self._canonical_word_transform:
            word = self._canonical_word_transform[up_word]
        elif len(word) <= 2 and word.isalpha():
            word = word.upper()
        elif word.isalpha():
            word = word.capitalize()

        if word.count('-'):
            # assent name has hyphens
            word = word.replace('-', '.', 1)
            word = word.upper()
        return word

    @staticmethod
    def _looks_opaque_identifier(component: str):
        if re.fullmatch(r'ADR\d+', component):
            return False
        if re.fullmatch(r'0X[0-9A-F]+', component):
            return True
        if len(component) >= MimirNameRules.OPAQUE_IDENTIFIER_MIN_LENGTH \
                and any(c.isdigit() for c in component):
            return True
        return bool(re.search(r'\d', component) and re.search(r'[A-Z]', component))

    @staticmethod
    def _format_opaque_identifier(component: str):
        if component.startswith('THORPUB') and len(component) > len('THORPUB') + 7:
            return f'{component[:len("THORPUB") + 3]}...{component[-4:]}'
        return component

    def _split_plain_component(self, component: str, preserve_unknown_suffix=False):
        if not component:
            return []

        adr_match = re.fullmatch(r'ADR0*(\d+)', component)
        if adr_match:
            return [f'ADR-{adr_match.group(1)}']
        if component.isdigit() or self._looks_opaque_identifier(component):
            return [self._format_opaque_identifier(component)]

        if self._word_splitter is None:
            self._rebuild_word_splitter()
        split_words = list(self._word_splitter.split(component))
        is_known_word = component in self.known_words \
            or component in self.rules_word_transform \
            or component in self._canonical_word_transform
        if preserve_unknown_suffix and len(component) <= 8 and not is_known_word \
                and (len(split_words) == 1 or all(len(word) <= 3 for word in split_words)):
            return [component]
        return [self._transform_each_word(word) for word in split_words]

    def _try_asset_mimir_name(self, name: str):
        match = re.fullmatch(
            r'(PAUSELPDEPOSIT|POL|TORANCHOR)-([A-Z0-9]+)-([A-Z0-9]+)(?:-.+)?',
            name,
        )
        if not match:
            return None

        prefix, chain, symbol = match.groups()
        asset = chain if chain == symbol else f'{chain}.{symbol}'
        return f'{self.ASSET_KEY_PREFIXES[prefix]} {asset}'

    @property
    def _structural_transforms(self):
        # Hyphenated entries are chain assets or other indivisible protocol
        # identifiers. Prefix transforms such as ``POL-`` are deliberately
        # excluded; their trailing key is meaningful structure, not content.
        return sorted(
            (
                word for word in self.rules_word_transform
                if '-' in word and not word.endswith('-')
            ),
            key=len,
            reverse=True,
        )

    def try_deducting_mimir_name(self, name: str, glue=' '):
        name = name.upper()
        asset_name = self._try_asset_mimir_name(name)
        if asset_name:
            return asset_name

        words = []
        position = 0
        structural_transforms = self._structural_transforms

        while position < len(name):
            if name[position] in '-.':
                position += 1
                continue

            structural_word = next(
                (
                    word for word in structural_transforms
                    if name.startswith(word, position)
                    and (position + len(word) == len(name)
                         or name[position + len(word)] in '-.')
                ),
                None,
            )
            if structural_word:
                words.append(self._transform_each_word(structural_word))
                position += len(structural_word)
                continue

            end = position
            while end < len(name) and name[end] not in '-.':
                end += 1
            words.extend(self._split_plain_component(
                name[position:end],
                preserve_unknown_suffix=position > 0,
            ))
            position = end

        return glue.join(words)

    def name_to_human(self, name: str):
        name = name.upper()
        r = (
                self.rules.get('translate', {}).get(name)
                or self._canonical_names.get(name)
                or self.try_deducting_mimir_name(name)
                or name
        )

        # fix issues like "Ragnarok . BNB.ETHBULL-D33"
        r = r.replace(' . ', ' ')

        return r

    def get_mimir_units(self, name):
        if 'types' not in self.rules:
            return ''

        name = name.upper()
        if re.fullmatch(r'ADR\d+', name):
            return MimirUnits.UNITS_VOTE_FOR_AGAINST
        if name in self.rules['types']['rune']:
            return MimirUnits.UNITS_RUNES
        elif name in self.rules['types']['blocks']:
            return MimirUnits.UNITS_BLOCKS
        elif name in self.rules['types']['until_block']:
            return MimirUnits.UNITS_UNTIL_BLOCK
        elif name in self.rules['types']['bool']:
            return MimirUnits.UNITS_BOOL
        elif name in self.rules['types']['usd']:
            return MimirUnits.UNITS_USD
        elif name in self.rules['types']['basis_points']:
            return MimirUnits.UNITS_BASIS_POINTS
        elif self.get_special_voting_value_map(name):
            return MimirUnits.UNITS_SPECIAL_MAP
        else:
            return ''
