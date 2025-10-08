from models.memo import ActionType


class MidgardURLGenV2:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')

    LIQUIDITY_TX_TYPES = ['withdraw', 'addLiquidity']

    def url_for_tx(self, offset=0, count=50, address=None, tx_type=None, txid=None, asset=None,
                   next_page_token='') -> str:
        url = f'{self.base_url}/v2/actions?offset={offset}&limit={count}'
        if address:
            url += f'&address={address}'
        if tx_type:
            if isinstance(tx_type, ActionType):
                # ActionType is an Enum, so get the value
                tx_type = tx_type.value
            elif isinstance(tx_type, (list, tuple)):
                # Convert all ActionType to string
                tx_type = ','.join(
                    t.value if isinstance(t, ActionType) else str(t)
                    for t in tx_type
                )
            url += f'&type={tx_type}'
        if txid:
            url += f'&txid={txid}'
        if asset:
            url += f'&asset={asset}'

        return url

    def url_for_next_page(self, next_page_token):
        return f'{self.base_url}/v2/actions?nextPageToken={next_page_token}'

    @staticmethod
    def bool_flag(b: bool):
        return 'true' if b else 'false'

    def url_for_pool_depth_history(self, pool, from_ts, to_ts) -> str:
        return f"{self.base_url}/v2/history/depths/{pool}?interval=day&from={from_ts}&to={to_ts}"

    def url_for_swap_history(self, from_ts=0, to_ts=0, count=10, interval='day', pool=None) -> str:
        if from_ts and to_ts:
            spec = f'from={from_ts}&to={to_ts}'
        else:
            spec = f'count={count}'
        if pool:
            spec += f'&pool={pool}'
        return f"{self.base_url}/v2/history/swaps?interval={interval}&{spec}"

    def url_for_earnings_history(self, from_ts=0, to_ts=0, count=10, interval='day') -> str:
        spec = ''
        if from_ts and to_ts:
            spec = f'from={from_ts}&to={to_ts}'
        elif count:
            spec = f'count={count}'
        if interval:
            spec += f"&interval={interval}"
        return f"{self.base_url}/v2/history/earnings?{spec}"

    def url_for_address_pool_membership(self, address) -> str:
        return f"{self.base_url}/v2/member/{address}"

    def url_network(self):
        return f'{self.base_url}/v2/network'

    def url_stats(self):
        return f'{self.base_url}/v2/stats'

    def url_pools_info(self, period=None):
        url = f'{self.base_url}/v2/pools'
        return f'{url}?period={period}' if period else url

    def url_pool_info(self, pool, period=None):
        url = f'{self.base_url}/v2/pool/{pool}'
        return f'{url}?period={period}' if period else url

    def url_affiliate_history(self, from_ts=0, to_ts=0, count=0, interval='day') -> str:
        spec = ''
        if from_ts and to_ts:
            spec = f'from={from_ts}&to={to_ts}'
        elif count:
            spec = f'count={count}'
        if interval:
            spec += f"&interval={interval}"
        return f'{self.base_url}/v2/history/affiliate?{spec}'

    def url_pool_depth_history(self, pool: str, count=30, interval='day') -> str:
        return f'{self.base_url}/v2/history/depths/{pool}?count={count}&interval={interval}'


free_url_gen = MidgardURLGenV2('')
