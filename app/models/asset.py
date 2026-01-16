import dataclasses
from collections import defaultdict
from copy import copy
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Union

from lib.constants import RUNE_DENOM, Chains, NATIVE_RUNE_SYMBOL


class Delimiter:
    SYNTH = '/'
    """Synth assets use '/' as delimiter (BTC/BTC)"""

    TRADE = '~'
    """Trade assets use '~' as delimiter (BTC~BTC)"""

    NATIVE = '.'
    """Native assets use '.' as delimiter (THOR.RUNE, BTC.BTC)"""

    SECURED = '-'
    """
        Secured assets use '-' as delimiter (ETH-ETH).
        See: https://docs.thorchain.org/thorchain-finance/secured-assets
    """

    ALL_DELIMITERS = {NATIVE, TRADE, SYNTH, SECURED}


class AssetKind(Enum):
    NATIVE = 'native'
    """Native Assets are L1 assets (eg BTC) available on its native L1 (eg Bitcoin Network)."""

    SYNTH = 'synth'
    """
    THORChain synthetics are fully collateralized while they exist and switch to a 1:1 peg upon redemption.
    See: https://docs.thorchain.org/frequently-asked-questions/asset-types#synthetic-assets
    Attention! Synthetic assets are now suspended on the network due to THORFi being on pause.
    Please use trade and secured assets instead.
    """
    # todo: fill in the details for derived assets

    TRADE = 'trade'
    """
    Trade Assets, a new class of primitives on THORChain, offer double the capital efficiency of synthetic assets, 
    enhancing arbitrage and high-frequency trading. They settle with THORChain’s block speed and cost, enabling 
    6-second finality swaps without high fees. Redeemable anytime with no slippage, Trade Assets emulate centralized 
    exchange trading but maintain on-chain transparency and security. Custodied by THORChain outside of liquidity pools, 
    they provide user credits while holding funds 1:1 as L1 assets until withdrawal, making THORChain more user-friendly 
    for active traders.
    See: https://docs.thorchain.org/frequently-asked-questions/asset-types#trade-assets
    """

    DERIVED = 'derived'
    """
    THORChain derived assets.
    See: https://docs.thorchain.org/frequently-asked-questions/asset-types#derived-assets
    """

    SECURED = 'secured'
    """
    Secure Assets allow L1 tokens to be deposited to THORChain, creating a new native asset, which can be transferred 
    between accounts, over IBC and integrated with CosmWasm smart contracts using standard Cosmos SDK messages. 
    They also replace Trade Assets. 
    See: https://docs.thorchain.org/thorchain-finance/secured-assets
    """

    UNKNOWN = 'unknown'
    """Unknown asset type."""

    @property
    def delimiter(self):
        """
        Return the delimiter based on the asset kind.
        """
        if self == AssetKind.SYNTH:
            return Delimiter.SYNTH
        elif self == AssetKind.TRADE:
            return Delimiter.TRADE
        elif self == AssetKind.SECURED:
            return Delimiter.SECURED
        else:
            return Delimiter.NATIVE

    @classmethod
    def recognize(cls, asset_str: str) -> 'AssetKind':
        """
            Detects the asset type based on the first delimiter in the asset string.

            :param asset_str: The asset string (e.g., "ETH.ETH", "BTC-BTC", "XRP~XRP").
            :return: The asset type: "trade" for "~", "secured" for "-", "native" for ".", or "unknown" if no valid delimiter is found.
            :rtype AssetKind
        """
        for char in asset_str:
            if char in Delimiter.ALL_DELIMITERS:
                return _DELIMITER_TABLE[char]
        return cls.UNKNOWN

    @classmethod
    def restore_asset_type(cls, original: str, name: str):
        if not name or not original:
            return name

        if original == name:
            return original

        asset_type = cls.recognize(original)

        if asset_type == AssetKind.TRADE:
            return name.replace(Delimiter.NATIVE, Delimiter.TRADE, 1)
        elif asset_type == AssetKind.SYNTH:
            return name.replace(Delimiter.NATIVE, Delimiter.SYNTH, 1)
        elif asset_type == AssetKind.SECURED:
            return name.replace(Delimiter.NATIVE, Delimiter.SECURED, 1)
        else:
            return name


_DELIMITER_TABLE = {
    Delimiter.TRADE: AssetKind.TRADE,
    Delimiter.SECURED: AssetKind.SECURED,
    Delimiter.NATIVE: AssetKind.NATIVE,
    Delimiter.SYNTH: AssetKind.SYNTH,
}


def is_trade_asset(asset: str):
    return AssetKind.recognize(asset) == AssetKind.TRADE


def normalize_asset(asset: str):
    kind = AssetKind.recognize(asset)
    asset = asset.replace(kind.delimiter, Delimiter.NATIVE, 1).strip()
    return asset


@dataclass
class Asset:
    chain: str = ''
    name: str = ''
    tag: str = ''
    is_synth: bool = False
    is_virtual: bool = False
    is_trade: bool = False
    is_secured: bool = False

    @property
    def valid(self):
        return bool(self.chain) and bool(self.name)

    def __post_init__(self):
        if self.chain and not self.name:
            source = self.chain
            a = self.from_string(source)
            self.chain = a.chain
            self.name = a.name
            self.tag = a.tag
            self.is_synth = a.is_synth
            self.is_virtual = a.is_virtual
            self.is_trade = a.is_trade
            self.is_secured = a.is_secured
            # don't forget to copy the rest of fields if you add them!

    @staticmethod
    def get_name_tag(name_and_tag_str):
        components = name_and_tag_str.split('-', maxsplit=2)
        if len(components) == 2:
            return components
        else:
            return name_and_tag_str, ''

    def upper(self):
        asset = copy(self)
        asset.chain = asset.chain.upper()
        asset.name = asset.name.upper()
        asset.tag = asset.tag.upper()
        return asset

    @classmethod
    def from_string(cls, asset: str):
        if isinstance(asset, Asset):
            return asset

        if not isinstance(asset, str):
            raise ValueError('Asset must be a string')

        if asset == RUNE_DENOM:
            return copy(AssetRUNE)

        is_synth, is_trade, is_secured = False, False, False
        kind = AssetKind.recognize(asset)
        match kind:
            case AssetKind.SYNTH:
                is_synth = True
            case AssetKind.TRADE:
                is_trade = True
            case AssetKind.SECURED:
                is_secured = True

        try:
            separator = kind.delimiter
            chain, name_and_tag = asset.split(separator, maxsplit=1)
            name, tag = cls.get_name_tag(name_and_tag)
            chain = str(chain).upper()
            name = str(name).upper()
            tag = str(tag).upper()
            is_virtual = chain == 'THOR' and name != 'RUNE'
            # is_app_layer = chain == 'X' and is_synth
            return cls(chain, name, tag, is_synth, is_virtual, is_trade, is_secured=is_secured)
        except ValueError:
            # not enough values to unpack. It's a string like "ETH" or "BTC"
            return cls.gas_asset_from_chain(str(asset).upper())

    PILL = '💊'
    TRADE = '🔄'

    @property
    def pretty_str(self):
        pn = self._pretty_name.upper()
        if self.is_app_layer:
            return pn
        elif self.is_synth:
            return f'synth {pn}'
        elif self.is_trade:
            return f'trade {pn}'
        elif self.is_secured:
            return f'secured {pn}'
        else:
            return pn

    @property
    def _pretty_name(self):
        sep = self.separator_symbol
        str_me = str(self)
        if is_rune(str_me):
            return 'Rune ᚱ'
        elif is_ruji(str_me):
            return 'RUJI'
        elif normalize_asset(str_me) in self.ABBREVIATE_GAS_ASSETS:
            return self.name  # Not ETH.ETH, just ETH
        else:
            return f'{self.chain}{sep}{self.name}'

    @property
    def pretty_str_no_emoji(self):
        return self.pretty_str.replace(self.PILL, '')

    @property
    def shortest(self):
        return f'{self.chain}.{self.name}'

    @property
    def full_name(self):
        if self.valid:
            return f'{self.name}-{self.tag}' if self.tag else self.name
        else:
            return self.name

    @property
    def separator_symbol(self):
        if self.is_trade:
            return Delimiter.TRADE
        elif self.is_synth:
            return Delimiter.SYNTH
        elif self.is_secured:
            return Delimiter.SECURED
        else:
            return Delimiter.NATIVE

    @property
    def to_canonical(self):
        return f'{self.chain}{self.separator_symbol}{self.full_name}'

    @property
    def first_filled_component(self):
        return self.chain or self.name or self.tag

    @property
    def native_pool_name(self):
        return f'{self.chain}.{self.full_name}' if self.valid else self.name

    @property
    def l1_asset(self):
        return dataclasses.replace(self, is_synth=False, is_trade=False, is_virtual=False, is_secured=False)

    def __str__(self):
        return self.to_canonical

    @classmethod
    def to_L1_pool_name(cls, asset: str):
        return cls.from_string(asset).native_pool_name

    @property
    def is_gas_asset(self):
        return self.gas_asset_from_chain(self.chain) == self

    @property
    def is_app_layer(self):
        return self.chain.upper() == "X" and self.is_synth

    SHORT_NAMES = {
        'a': 'AVAX.AVAX',
        'b': 'BTC.BTC',
        'c': 'BCH.BCH',
        'n': 'BNB.BNB',
        's': 'BSC.BNB',
        'd': 'DOGE.DOGE',
        'e': 'ETH.ETH',
        'l': 'LTC.LTC',
        'r': 'THOR.RUNE',
        'f': 'BASE.ETH',
        'x': 'XRP.XRP',
        'g': 'GAIA.ATOM',
        'tr': 'TRON.TRX',
    }

    ABBREVIATE_GAS_ASSETS = {
        'ETH.ETH', 'BTC.BTC', 'LTC.LTC', 'AVAX.AVAX', 'DOGE.DOGE', 'GAIA.ATOM', 'BSC.BNB', 'BCH.BCH', 'XRP.XRP',
    }

    GAS_ASSETS = {
        Chains.ATOM: 'ATOM',
        Chains.THOR: 'RUNE',
        Chains.BSC: 'BNB',
        Chains.BASE: 'ETH',
        Chains.TRON: 'TRX',
        # to be continued...
    }

    @classmethod
    def gas_asset_from_chain(cls, chain: str):
        chain = chain.upper()
        name = cls.GAS_ASSETS.get(chain, chain)
        return cls(chain, name)


AssetRUNE = Asset.from_string(NATIVE_RUNE_SYMBOL)


def is_rune(asset: Union[Asset, str]):
    if isinstance(asset, Asset):
        asset = str(asset)
    asset = asset.strip()
    return asset.lower() in ('r', RUNE_DENOM) or asset.upper() == NATIVE_RUNE_SYMBOL


def is_ruji(asset: Union[Asset, str]):
    if isinstance(asset, Asset):
        asset = str(asset)
    asset = asset.strip()
    return asset.lower() == 'x/ruji'


def is_ambiguous_asset(asset: Union[str, Asset], among_assets: Iterable[str] = None):
    asset = Asset.from_string(asset)
    if asset.gas_asset_from_chain(asset.chain) != asset.l1_asset:
        return True

    if among_assets is None:
        return False

    ambiguous_tracker = defaultdict(set)
    for a in among_assets:
        name = Asset.from_string(a).name
        ambiguous_tracker[name].add(a)

    return len(ambiguous_tracker.get(asset.name, [])) > 1
