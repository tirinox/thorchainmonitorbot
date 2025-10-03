import asyncio

from jobs.fetch.base import BaseFetcher
from lib.depcont import DepContainer
from models.mimir import MimirHolder
from models.tcy import TcyFullInfo, TcyStatus, VNXTcyData, TcyMimirs


class TCYInfoFetcher(BaseFetcher):
    def __init__(self, deps: DepContainer):
        period = deps.cfg.as_interval('tcy.fetch_period', '1h')
        super().__init__(deps, sleep_period=period)
        self.deps = deps

    VNX_URL_TCY_INFO = 'https://vanaheimex.com/api/tcyInfo'

    async def get_vnx_data(self) -> VNXTcyData:
        async with self.deps.session.get(self.VNX_URL_TCY_INFO) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return VNXTcyData(**data)

    async def get_tcy_status_from_mimir(self) -> TcyStatus:
        mimir_tuple = await self.deps.mimir_cache.get()
        mimir = MimirHolder().update(mimir_tuple, [], with_voting=False)

        return TcyStatus(
            halt_claiming=mimir.get_constant(TcyMimirs.HALT_CLAIMING),
            halt_staking=mimir.get_constant(TcyMimirs.HALT_STAKING),
            halt_trading=mimir.get_constant(TcyMimirs.HALT_TRADING),
            halt_unstaking=mimir.get_constant(TcyMimirs.HALT_UNSTAKING),
            halt_claiming_swap=mimir.get_constant(TcyMimirs.HALT_CLAIMING_SWAP),
            halt_stake_distribution=mimir.get_constant(TcyMimirs.HALT_STAKE_DISTRIBUTION)
        )

    async def fetch(self) -> TcyFullInfo:
        vnx_data, status = await asyncio.gather(
            self.get_vnx_data(),
            self.get_tcy_status_from_mimir()
        )
        return TcyFullInfo(
            vnx=vnx_data,
            status=status
        )

    # stake earning = interval.liquidityFees / 1e8 * 10% * runePriceUSD
