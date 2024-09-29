import logging
import os

import web3
from PIL import Image

from lib.constants import *
from models.asset import Asset
from lib.utils import download_file

logger = logging.getLogger(__name__)


def convert_eth_address_to_case_checksum(eth_address: str) -> str:
    eth_address = eth_address[2:].lower()  # strip 0x and lower case

    address_hash = web3.Web3.keccak(eth_address.encode('utf-8')).hex()[2:]

    new_address = ''
    for hash_symbol, symbol in zip(address_hash, eth_address):
        if int(hash_symbol, 16) > 7:
            new_address += symbol.upper()
        else:
            new_address += symbol

    return '0x' + new_address


class CryptoLogoDownloader:
    LOGO_WIDTH, LOGO_HEIGHT = 128, 128
    COIN_BASE_URL = 'https://raw.githubusercontent.com/trustwallet/assets/master/blockchains'
    UNKNOWN_LOGO = f'unknown.png'

    CONTRACT = 'contract'

    CHAIN_TO_NAME = {
        Chains.BNB: 'binance',
        Chains.BTC: 'bitcoin',
        Chains.LTC: 'litecoin',
        Chains.BCH: 'bitcoincash',
        Chains.ETH: 'ethereum',
        Chains.DOGE: 'doge',
        Chains.AVAX: 'avalanchex',
        Chains.AVAX + CONTRACT: 'avalanchec',
        Chains.ATOM: 'cosmos',
        Chains.BSC: 'smartchain',
    }

    # Mapping: Chain to the asset name of the logo of this chain
    #   that often corresponds to the logo of the governance token
    CHAIN_TO_LOGO_ASSET = {
        Chains.ETH: 'ETH.ETH',
        Chains.BSC: 'BSC.BNB',
        Chains.AVAX: 'AVAX.AVAX',
        Chains.ATOM: 'GAIA.ATOM',
        # to be continued...
    }

    TEST_ASSET_MAPPING = {
        ETH_USDT_TEST_SYMBOL: ETH_USDT_SYMBOL,
    }

    def path_to_local_storage(self, path):
        return os.path.join(self.base_dir, path)

    def path_to_local_coin_image(self, coin):
        return self.path_to_local_storage(f'{coin}.png')

    def __init__(self, data_dir: str) -> None:
        self.base_dir = data_dir

    @classmethod
    def image_url(cls, asset: str):
        if asset in cls.TEST_ASSET_MAPPING:  # fix for unknown test assets
            asset = cls.TEST_ASSET_MAPPING[asset]

        a = Asset.from_string(asset)

        chain_name = ''
        if a.tag:
            chain_name = cls.CHAIN_TO_NAME.get(a.chain + cls.CONTRACT)

        if not chain_name:
            chain_name = cls.CHAIN_TO_NAME.get(a.chain)

        if a.is_gas_asset:  # e.g. BNB.BNB, BTC.BTC, GAIA.ATOM
            path = f'{chain_name}/info/logo.png'
        else:
            if a.chain != Chains.BNB:
                address = convert_eth_address_to_case_checksum(a.tag)  # fix for CaSe checksum
            else:
                address = a.full_name
            path = f'{chain_name}/assets/{address}/logo.png'

        return f'{cls.COIN_BASE_URL}/{path}'

    async def _download_logo(self, asset):
        if not asset:
            raise FileNotFoundError

        url = self.image_url(asset)
        if not url:
            raise FileNotFoundError

        target_path = self.path_to_local_coin_image(asset)
        await download_file(url, target_path)

        # thumbnail
        logo = Image.open(target_path).convert("RGBA")
        logo.thumbnail((self.LOGO_WIDTH, self.LOGO_HEIGHT))
        with open(target_path, 'wb') as f:
            logo.save(f, 'png')

    async def get_or_download_logo_cached(self, asset, forced=False):
        try:
            local_path = self.path_to_local_coin_image(asset)
            if forced or not os.path.exists(local_path):
                await self._download_logo(asset)
            logo = Image.open(local_path).convert("RGBA")
        except Exception as e:
            logo = Image.open(self.path_to_local_storage(self.UNKNOWN_LOGO))
            logger.error(f'error ({e}) loading logo for "{asset}". using the default one...')

        if logo.size != (self.LOGO_WIDTH, self.LOGO_HEIGHT):
            logo.thumbnail((self.LOGO_WIDTH, self.LOGO_HEIGHT))
        return logo


    async def get_logo_for_chain(self, chain, forced=False):
        # for example: for ARB.XXX-0X123123, we need to get the logo for ARB
        virtual_asset = self.CHAIN_TO_LOGO_ASSET.get(chain)
        if not virtual_asset:
            return
        return await self.get_or_download_logo_cached(virtual_asset, forced)