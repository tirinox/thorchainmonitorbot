import logging
import os
import sha3
import aiofiles
import aiohttp
from PIL import Image

from services.lib.constants import *

logger = logging.getLogger(__name__)


def convert_eth_address_to_case_checksum(eth_address: str) -> str:
    eth_address = eth_address[2:].lower()  # strip 0x and lower case
    address_hash = sha3.keccak_256(eth_address.encode('utf-8')).hexdigest()

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

    CHAIN_TO_NAME = {
        Chains.BNB: 'binance',
        Chains.BTC: 'bitcoin',
        Chains.LTC: 'litecoin',
        Chains.BCH: 'bitcoincash',
        Chains.DOT: 'polkadot',
        Chains.ETH: 'ethereum',
        Chains.ZIL: 'zilliqa',
    }

    TEST_ASSET_MAPPING = {
        BNB_USDT_TEST_SYMBOL: BNB_USDT_SYMBOL,
        BNB_BUSD_TEST_SYMBOL: BNB_BUSD_SYMBOL,
        BNB_RUNE_TEST_SYMBOL: BNB_RUNE_SYMBOL,
        ETH_USDT_TEST_SYMBOL: ETH_USDT_SYMBOL,
        ETH_RUNE_SYMBOL_TEST: ETH_RUNE_SYMBOL,
    }

    def get_full_path(self, path):
        return os.path.join(self.base_dir, path)

    def coin_path(self, coin):
        return self.get_full_path(f'{coin}.png')

    def __init__(self, data_dir: str) -> None:
        self.base_dir = data_dir

    @classmethod
    def image_url(cls, asset: str):
        if asset in cls.TEST_ASSET_MAPPING:  # fix for unknown test assets
            asset = cls.TEST_ASSET_MAPPING[asset]

        chain, asset, *_ = asset.split('.')

        chain_name = cls.CHAIN_TO_NAME.get(chain)
        if asset == chain:  # e.g. BNB.BNB, BTC.BTC
            path = f'{chain_name}/info/logo.png'
        else:
            name, address = asset.split('-')[:2]
            address = convert_eth_address_to_case_checksum(address)  # fix for CaSe checksum
            path = f'{chain_name}/assets/{address}/logo.png'

        return f'{cls.COIN_BASE_URL}/{path}'

    async def _download_logo(self, asset):
        if not asset:
            raise FileNotFoundError

        async with aiohttp.ClientSession() as session:
            url = self.image_url(asset)
            if not url:
                raise FileNotFoundError

            logger.info(f'Downloading logo for {asset} from {url}...')
            async with session.get(url) as resp:
                if resp.status == 200:
                    f = await aiofiles.open(self.coin_path(asset), mode='wb')
                    await f.write(await resp.read())
                    await f.close()

    async def get_or_download_logo_cached(self, asset):
        try:
            local_path = self.coin_path(asset)
            if not os.path.exists(local_path):
                await self._download_logo(asset)
            logo = Image.open(local_path).convert("RGBA")
        except Exception:
            logo = Image.open(self.get_full_path(self.UNKNOWN_LOGO))
            logger.error(f'error loading logo for "{asset}". using the default one...')
        logo.thumbnail((self.LOGO_WIDTH, self.LOGO_HEIGHT))  # fixme: move thumbnail to download_logo
        return logo
