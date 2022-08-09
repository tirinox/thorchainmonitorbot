from localization.base import BaseLocalization
from services.jobs.fetch.circulating import RuneCirculatingSupply
from services.lib.date_utils import today_str
from services.lib.draw_utils import img_to_bio
from services.lib.plot_graph import PlotGraph
from services.lib.utils import async_wrap
from services.models.killed_rune import KilledRuneEntry


class SupplyPictureGenerator:
    WIDTH = 1024
    HEIGHT = 768

    def __init__(self, loc: BaseLocalization, supply: RuneCirculatingSupply, killed_rune: KilledRuneEntry):
        self.supply = supply
        self.killed = killed_rune
        self.loc = loc

    async def get_picture(self):
        return await self._get_picture_sync()

    @async_wrap
    def _get_picture_sync(self):
        today = today_str()
        gr = PlotGraph(self.WIDTH, self.HEIGHT)

        gr.draw.rectangle(((100, 100), (200, 150)), 'red')

        gr.title = 'THORChain Rune supply'  # todo: loc

        return img_to_bio(gr.finalize(), f'thorchain_supply_{today}.png')
