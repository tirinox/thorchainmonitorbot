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

    def url_for_swap_history(self, from_ts=0, to_ts=0, count=10, interval='day') -> str:
        if from_ts and to_ts:
            spec = f'from={from_ts}&to={to_ts}'
        else:
            spec = f'count={count}'
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

    def url_for_savers_history(self, pool: str, from_ts=0, to_ts=0, count=10, interval='day') -> str:
        params = []

        if interval:
            params.append(f"interval={interval}")
        if count:
            params.append(f"count={count}")
        if from_ts:
            params.append(f"from={from_ts}")
        if to_ts:
            params.append(f"to={to_ts}")

        return f"{self.base_url}/v2/history/savers/{pool}?{'&'.join(params)}"

    def url_for_address_pool_membership(self, address, show_savers=False) -> str:
        return f"{self.base_url}/v2/member/{address}?showSavers={self.bool_flag(show_savers)}"

    def url_network(self):
        return f'{self.base_url}/v2/network'

    def url_stats(self):
        return f'{self.base_url}/v2/stats'

    def url_pool_info(self, period=None):
        if period:
            return f'{self.base_url}/v2/pools?period={period}'
        return f'{self.base_url}/v2/pools'

    def url_borrowers(self):
        return f'{self.base_url}/v2/borrowers'

    def url_borrower(self, address):
        return f'{self.base_url}/v2/borrower/{address}'


free_url_gen = MidgardURLGenV2('')
