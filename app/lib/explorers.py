from lib.constants import NetworkIdents, Chains
from models.asset import Asset


def thorchain_net_tx(tx_id: str):
    return f'https://thorchain.net/tx/{tx_id}'


def thorchain_net_address(address: str):
    return f'https://thorchain.net/address/{address}'


def get_explorer_url_to_address(network_id, pool_or_chain: str, address: str, tab=None):
    chain = Asset(pool_or_chain).first_filled_component

    is_live = not NetworkIdents.is_test(network_id)
    if chain == Chains.THOR:
        url = f"https://runescan.io/address/{address}"
        if tab:
            url += f'?tab={tab}'
        return url
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
    elif chain == Chains.BSC:
        return f'https://bscscan.com/address/{address}'
    elif chain == Chains.BASE:
        return f'https://basescan.org/address/{address}'
    elif chain == Chains.XRP:
        return f'https://xrpscan.com/account/{address}'
    elif chain == Chains.TRON:
        return f'https://tronscan.org/#/address/{address}'
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
        return f"https://runescan.io/tx/{tx_id}"
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
    elif chain == Chains.BSC:
        return f'https://bscscan.com/tx/{tx_id}'
    elif chain == Chains.BASE:
        return f'https://basescan.org/tx/{tx_id}'
    elif chain == Chains.XRP:
        return f'https://xrpscan.com/tx/{tx_id}'
    elif chain == Chains.TRON:
        return f'https://tronscan.org/#/transaction/{tx_id}'
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


def get_thoryield_address(address: str, chain: str = Chains.THOR):
    chain = chain.lower()
    return f'https://app.thoryield.com/lp?{chain}={address}'


def get_ip_info_link(ip_address):
    return f'https://www.infobyip.com/ip-{ip_address}.html'
