from lib.logs import WithLogger
from models.affiliate import AffiliateHistoryResponse

VANAHEIMIX_DEFAULT_URL = 'https://vanaheimex.com/'


class VanaheimixDataSource(WithLogger):
    def __init__(self, session, base_url: str = VANAHEIMIX_DEFAULT_URL):
        super().__init__()
        self.base_url = base_url.rstrip('/')
        self.session = session

    async def _request(self, sub_path: str):
        url = f'{self.base_url}/{sub_path.lstrip("/")}'
        self.logger.info(f'Requesting Vanaheimix data from {url}')
        async with self.session.get(url) as response:
            if response.status != 200:
                raise ValueError(f'Error fetching data from {url}: {response.status}')
            return await response.json()

    async def get_affiliate_fees(self, interval: str = 'day', count: int = 7):
        sub_path = f'affiliate?interval={interval}&count={count}'
        raw = await self._request(sub_path)
        return AffiliateHistoryResponse(**raw)
