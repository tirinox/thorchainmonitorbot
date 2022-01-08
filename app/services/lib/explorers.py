from services.lib.constants import NetworkIdents, Chains
from services.lib.money import Asset


def get_explorer_url_to_address(network_id, pool_or_chain: str, address: str):
    chain = Asset(pool_or_chain).first_filled_component

    is_live = not NetworkIdents.is_test(network_id)
    if chain == Chains.THOR:
        if network_id == NetworkIdents.TESTNET_MULTICHAIN:
            return f"https://main.d2rtjbuh4gx2cf.amplifyapp.com/#/address/{address}"
        elif network_id == NetworkIdents.CHAOSNET_MULTICHAIN:
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
    elif chain == Chains.BCH:
        return f'https://www.blockchain.com/bch/address/{address}' if is_live else \
            f'https://www.blockchain.com/bch-testnet/address/{address}'
    elif chain == Chains.LTC:
        return f'https://blockchair.com/litecoin/address/{address}' if is_live else \
            f'https://tltc.bitaps.com/{address}'
    elif chain == Chains.DOGE:
        return f'https://dogechain.info/address/{address}'
    else:
        url = f'https://www.google.com/search?q={chain}+explorer'
        return url if is_live else f'{url}+test'


def get_explorer_url_to_tx(network_id, pool_or_chain: str, tx_id: str):
    chain = Asset(pool_or_chain).first_filled_component

    is_live = not NetworkIdents.is_test(network_id)
    if chain == Chains.THOR:
        if network_id == NetworkIdents.TESTNET_MULTICHAIN:
            return f"https://main.d2rtjbuh4gx2cf.amplifyapp.com/#/txs/{tx_id}"
        elif network_id == NetworkIdents.CHAOSNET_MULTICHAIN:
            return f"https://www.thorchain.net/#/txs/{tx_id}"
    elif chain == Chains.BNB:
        return f'https://explorer.binance.org/tx/{tx_id}' if is_live else \
            f'https://testnet-explorer.binance.org/tx/{tx_id}'
    elif chain == Chains.ETH:
        if not tx_id.startswith('0x') and not tx_id.startswith('0X'):
            tx_id = '0x' + tx_id
        return f'https://etherscan.io/tx/{tx_id}' if is_live else \
            f'https://ropsten.etherscan.io/tx/{tx_id}'
    elif chain == Chains.BTC:
        return f'https://www.blockchain.com/btc/tx/{tx_id}' if is_live else \
            f'https://www.blockchain.com/btc-testnet/tx/{tx_id}'
    elif chain == Chains.BCH:
        return f'https://www.blockchain.com/bch/tx/{tx_id}' if is_live else \
            f'https://www.blockchain.com/bch-testnet/tx/{tx_id}'
    elif chain == Chains.LTC:
        return f'https://blockchair.com/litecoin/transaction/{tx_id}' if is_live else \
            f'https://tltc.bitaps.com/{tx_id}'
    elif chain == Chains.DOGE:
        return f'https://dogechain.info/tx/{tx_id.lower()}'
    else:
        url = f'https://www.google.com/search?q={chain}+explorer'
        return url if is_live else f'{url}+test'


def get_explorer_url_for_node(address: str):
    if address.lower().startswith('tthor'):
        return f'https://testnet.thorchain.net/#/nodes/{address}'
    else:
        return f'https://thorchain.net/#/nodes/{address}'
