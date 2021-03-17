from services.lib.constants import NetworkIdents


class ExploreAssets:
    RUNE = 'rune'
    ETH = 'eth'
    BTC = 'btc'
    LTC = 'ltc'
    BNB = 'bnb'


def get_explorer_url(network_id, asset, address):
    is_live = not NetworkIdents.is_test(network_id)
    if asset == ExploreAssets.RUNE:
        if network_id == NetworkIdents.TESTNET_MULTICHAIN:
            return f"https://main.d3mbd42yfy75lz.amplifyapp.com/#/address/{address}"  # todo
        elif network_id == NetworkIdents.CHAOSNET_MULTICHAIN:
            return f"https://main.d3mbd42yfy75lz.amplifyapp.com/#/address/{address}"  # todo
        elif network_id == NetworkIdents.CHAOSNET_BEP2CHAIN:
            return f"https://viewblock.io/thorchain/address/{address}"
    elif asset == ExploreAssets.BNB:
        return f'https://explorer.binance.org/address/{address}' if is_live else \
            f'https://testnet-explorer.binance.org/address/{address}'
    elif asset == ExploreAssets.ETH:
        return f'https://etherscan.io/address/{address}' if is_live else \
            f'https://ropsten.etherscan.io/address/{address}'
    elif asset == ExploreAssets.BTC:
        return f'https://www.blockchain.com/btc/address/{address}' if is_live else \
            f'https://www.blockchain.com/btc-testnet/address/{address}'
    elif asset == ExploreAssets.LTC:
        return f'https://blockchair.com/litecoin/address/{address}' if is_live else \
            f'https://tltc.bitaps.com/{address}'
    else:
        return f'https://letmegooglethat.com/?q={asset}+explorer+{"" if is_live else "test"}'
