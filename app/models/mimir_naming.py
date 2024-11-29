import yaml

from lib.path import get_data_path

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

NEXT_CHAIN_KEY = 'NextChain'.upper()

MIMIR_DICT_FILENAME = f'{get_data_path()}/mimir_naming.yaml'


class MimirUnits:
    UNITS_RUNES = 'runes'
    UNITS_BLOCKS = 'blocks'
    UNITS_BOOL = 'bool'
    UNITS_NEXT_CHAIN = 'next_chain'
    UNITS_USD = 'usd'
    UNITS_BASIS_POINTS = 'basis_points'


class MimirNameRules:
    def __init__(self):
        self.rules = {}
        self.dict_word_sorted = []

    def load(self, filename):
        self.rules = self._load_mimir_naming_rules(filename)
        self.dict_word_sorted = list(sorted(self.rules.get('words', []), key=len, reverse=True))

    @staticmethod
    def _load_mimir_naming_rules(filename):
        with open(filename, 'r') as f:
            data = yaml.safe_load(f)

        data['words'] = [
            w.strip().upper() for w in data['words']
        ]
        data['word_transform'] = {
            k.strip().upper(): v
            for k, v in data.get('word_transform', {}).items()
        }

        return data

    @property
    def next_chain_voting_map(self):
        return self.rules.get('next_chain_voting_map', {})

    @property
    def rules_word_transform(self):
        return self.rules.get('word_transform', {})

    @property
    def excluded_from_voting(self):
        return self.rules.get('excluded_vote_keys', [])

    def _take_care_of_asset_name(self, word: str):
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

        for word in self.dict_word_sorted:
            word_len = len(word)
            while True:
                index = name.find(word)
                if index == -1:
                    break
                else:
                    components.append((index, word))
                    name = name.replace(word, ' ' * word_len)

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

        words = [self._take_care_of_asset_name(w) for w in words]

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
        name = name.upper()
        if name in self.rules['types']['rune']:
            return MimirUnits.UNITS_RUNES
        elif name in self.rules['types']['block']:
            return MimirUnits.UNITS_BLOCKS
        elif name in self.rules['types']['bool']:
            return MimirUnits.UNITS_BOOL
        elif name in self.rules['types']['usd']:
            return MimirUnits.UNITS_USD
        elif name == NEXT_CHAIN_KEY:
            return MimirUnits.UNITS_NEXT_CHAIN
        elif name in self.rules['types']['basis_points']:
            return MimirUnits.UNITS_BASIS_POINTS
        else:
            return ''
