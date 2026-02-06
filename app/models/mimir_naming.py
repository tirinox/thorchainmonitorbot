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
    UNITS_USD = 'usd'
    UNITS_BASIS_POINTS = 'basis_points'
    UNITS_INT = 'int'

    UNITS_SPECIAL_MAP = 'special_map'


class MimirNameRules:
    def __init__(self):
        self.rules = {}

    def load(self, filename):
        self.rules = self._load_mimir_naming_rules(filename)
        self.make_words_proper()
        self.sort_word_transform()

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

        if word.count('-'):
            # assent name has hyphens
            word = word.replace('-', '.', 1)
            word = word.upper()
        return word

    def try_deducting_mimir_name(self, name: str, glue=' '):
        components = []
        name = name.upper()

        word_offset = {}
        for word in self.known_words:
            word_len = len(word)
            while True:
                index = name.find(word, word_offset.get(word, 0))
                if index == -1:
                    break
                else:
                    word_offset[word] = index + 1
                    components.append((index, word))
                    name = name.replace(word, ' ' * word_len, 1)

        components.sort()  # sort by index

        if not components:
            return name.upper() + '?'

        words = []
        position = 0
        for index, word in components:
            if index > position:
                missing_word = name[position:index]
                words.append(missing_word.upper())
            words.append(word.capitalize())
            position = index + len(word)

        if position < len(name):
            words.append(name[position:].upper())

        words = [self._transform_each_word(w) for w in words]

        return glue.join(words)

    def name_to_human(self, name: str):
        r = (
                self.rules.get('translate', {}).get(name)
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
