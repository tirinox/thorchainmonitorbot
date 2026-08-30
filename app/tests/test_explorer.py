from lib.explorers import get_explorer_url_to_address, get_explorer_url_to_tx, NetworkIdents, Chains
from lib.texts import link_with_domain_text


def test_expl1():
    assert get_explorer_url_to_address(NetworkIdents.TESTNET_MULTICHAIN, 'DOT', 'jwfowwfjqjdqjqfo') == \
           'https://www.google.com/search?q=DOT+explorer+test'

    assert get_explorer_url_to_address(NetworkIdents.CHAOSNET_MULTICHAIN, 'DOT', 'jwfowwfjqjdqjqfo') == \
           'https://www.google.com/search?q=DOT+explorer'

    assert get_explorer_url_to_address(NetworkIdents.TESTNET_MULTICHAIN, Chains.BNB,
                                       'tbnb12ld7svh7wrwgvf0ll97xjnzp0qpeky97aqkpwc') == \
           'https://testnet-explorer.binance.org/address/tbnb12ld7svh7wrwgvf0ll97xjnzp0qpeky97aqkpwc'

    assert get_explorer_url_to_address(NetworkIdents.MAINNET, Chains.XMR, 'xmr-address') == \
           'https://xmrchain.net/search?value=xmr-address'
    assert get_explorer_url_to_address(NetworkIdents.MAINNET, Chains.ZEC, 'zec-address') == \
           'https://zcashblockexplorer.com/address/zec-address'
    assert get_explorer_url_to_tx(NetworkIdents.MAINNET, Chains.XMR, 'xmr-tx') == \
           'https://xmrchain.net/search?value=xmr-tx'
    assert get_explorer_url_to_tx(NetworkIdents.MAINNET, Chains.ZEC, 'zec-tx') == \
           'https://zcashblockexplorer.com/tx/zec-tx'


def uri_parse():
    assert link_with_domain_text(
        'https://viewblock.io/thorchain/address/bnb1nqcg6f8cfc6clhm8hac6002xq3h7l7gxh3qm34') == 'viewblock.io'
    assert link_with_domain_text('https://www.google.com/search?q=dot+explorer') == 'google.com'
    assert link_with_domain_text(
        'http://explorer.binance.org/address/bnb1pan55cahk054dnc2yp4xr9d0xzgvqey7d0upv2') == 'explorer.binance.org'
