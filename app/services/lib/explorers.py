from services.lib.constants import NetworkIdents, Chains
from services.lib.money import chain_name_from_pool


def get_explorer_url(network_id, pool_or_chain: str, address: str):
    chain = chain_name_from_pool(pool_or_chain).upper()

    is_live = not NetworkIdents.is_test(network_id)
    if chain == Chains.RUNE:
        if network_id == NetworkIdents.TESTNET_MULTICHAIN:
            return f"https://main.d3mbd42yfy75lz.amplifyapp.com/#/address/{address}"  # todo
        elif network_id == NetworkIdents.CHAOSNET_MULTICHAIN:
            return f"https://main.d3mbd42yfy75lz.amplifyapp.com/#/address/{address}"  # todo
        elif network_id == NetworkIdents.CHAOSNET_BEP2CHAIN:
            return f"https://viewblock.io/thorchain/address/{address}"
    elif chain == Chains.BNB:
        return f'https://explorer.binance.org/address/{address}' if is_live else \
            f'https://testnet-explorer.binance.org/address/{address}'
    elif chain == Chains.ETH:
        return f'https://etherscan.io/address/{address}' if is_live else \
            f'https://ropsten.etherscan.io/address/{address}'
    elif chain == Chains.BTC:
        return f'https://www.blockchain.com/btc/address/{address}' if is_live else \
            f'https://www.blockchain.com/btc-testnet/address/{address}'
    elif chain == Chains.LTC:
        return f'https://blockchair.com/litecoin/address/{address}' if is_live else \
            f'https://tltc.bitaps.com/{address}'
    else:
        url = f'https://www.google.com/search?q={chain}+explorer'
        return url if is_live else f'{url}+test'
