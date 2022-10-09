from services.lib.constants import NetworkIdents, Chains
from services.lib.money import Asset


def get_explorer_url_to_address(network_id, pool_or_chain: str, address: str):
    chain = Asset(pool_or_chain).first_filled_component

    is_live = not NetworkIdents.is_test(network_id)
    if chain == Chains.THOR:
        if network_id == NetworkIdents.TESTNET_MULTICHAIN:
            return f"https://main.d2rtjbuh4gx2cf.amplifyapp.com/#/address/{address}"
        elif network_id in (NetworkIdents.MAINNET, NetworkIdents.CHAOSNET_MULTICHAIN):
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
    elif chain == Chains.AVAX:
        return f'https://snowtrace.io/address/{address.lower()}'
    elif chain == Chains.ATOM:
        return f'https://www.mintscan.io/cosmos/account/{address.lower()}'
    else:
        url = f'https://www.google.com/search?q={chain}+explorer'
        return url if is_live else f'{url}+test'


def add_0x(tx_id: str):
    if not tx_id.startswith('0x') and not tx_id.startswith('0X'):
        tx_id = '0x' + tx_id
    return tx_id


def get_explorer_url_to_tx(network_id, pool_or_chain: str, tx_id: str):
    chain = Asset(pool_or_chain).first_filled_component

    is_live = not NetworkIdents.is_test(network_id)
    if chain == Chains.THOR:
        if network_id == NetworkIdents.TESTNET_MULTICHAIN:
            return f"https://main.d2rtjbuh4gx2cf.amplifyapp.com/#/txs/{tx_id}"
        elif network_id in (NetworkIdents.MAINNET, NetworkIdents.CHAOSNET_MULTICHAIN):
            # return f"https://www.thorchain.net/#/txs/{tx_id}"
            return f"https://viewblock.io/thorchain/tx/{tx_id}"
    elif chain == Chains.BNB:
        return f'https://explorer.binance.org/tx/{tx_id}' if is_live else \
            f'https://testnet-explorer.binance.org/tx/{tx_id}'
    elif chain == Chains.ETH:
        tx_id = add_0x(tx_id)
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
    elif chain == Chains.AVAX:
        tx_id = add_0x(tx_id.lower())
        return f'https://snowtrace.io/tx/{tx_id}'
    elif chain == Chains.ATOM:
        return f'https://www.mintscan.io/cosmos/txs/{tx_id.upper()}'
    else:
        url = f'https://www.google.com/search?q={chain}+explorer'
        return url if is_live else f'{url}+test'


def get_explorer_url_for_node(address: str):
    if address.lower().startswith('tthor'):
        return f'https://testnet.thorchain.net/#/nodes/{address}'
    else:
        return f'https://thorchain.net/#/nodes/{address}'


def get_pool_url(pool_name):
    return f'https://app.thorswap.finance/add/{pool_name}'


def get_thoryield_address(network: str, address: str, chain: str = Chains.THOR):
    if network == NetworkIdents.TESTNET_MULTICHAIN:
        return f'https://mctn.vercel.app/dashboard?{chain}={address}'
    else:
        chain = chain.lower()
        return f'https://app.thoryield.com/accounts?{chain}={address}'


def get_ip_info_link(ip_address):
    return f'https://www.infobyip.com/ip-{ip_address}.html'
