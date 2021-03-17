from services.lib.explorers import get_explorer_url, NetworkIdents, ExploreAssets


def test_expl1():
    assert get_explorer_url(NetworkIdents.CHAOSNET_BEP2CHAIN, ExploreAssets.BNB,
                            'bnb1pan55cahk054dnc2yp4xr9d0xzgvqey7d0upv2') == \
           'https://explorer.binance.org/address/bnb1pan55cahk054dnc2yp4xr9d0xzgvqey7d0upv2'
    assert get_explorer_url(NetworkIdents.TESTNET_MULTICHAIN, 'DOT', 'jwfowwfjqjdqjqfo') == \
           'https://www.google.com/search?q=dot+explorer+test'

    assert get_explorer_url(NetworkIdents.CHAOSNET_MULTICHAIN, 'DOT', 'jwfowwfjqjdqjqfo') == \
           'https://www.google.com/search?q=dot+explorer'

    assert get_explorer_url(NetworkIdents.CHAOSNET_BEP2CHAIN, ExploreAssets.RUNE,
                            'bnb1nqcg6f8cfc6clhm8hac6002xq3h7l7gxh3qm34') == \
           'https://viewblock.io/thorchain/address/bnb1nqcg6f8cfc6clhm8hac6002xq3h7l7gxh3qm34'

    assert get_explorer_url(NetworkIdents.TESTNET_MULTICHAIN, ExploreAssets.BNB,
                            'tbnb12ld7svh7wrwgvf0ll97xjnzp0qpeky97aqkpwc') == \
           'https://testnet-explorer.binance.org/address/tbnb12ld7svh7wrwgvf0ll97xjnzp0qpeky97aqkpwc'
