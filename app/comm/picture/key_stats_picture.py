import asyncio
from datetime import timedelta

from PIL import Image, ImageDraw

from comm.localization.manager import BaseLocalization
from comm.picture.common import BasePictureGenerator
from comm.picture.resources import Resources
from lib.constants import BTC_SYMBOL, ETH_SYMBOL, ETH_USDC_SYMBOL, ETH_USDT_SYMBOL, NATIVE_RUNE_SYMBOL
from lib.draw_utils import paste_image_masked, TC_LIGHTNING_BLUE, TC_YGGDRASIL_GREEN, \
    COLOR_OF_PROFIT, font_estimate_size, distribution_bar_chart
from lib.money import pretty_money, short_dollar, short_money
from lib.texts import bracketify
from lib.utils import async_wrap
from models.asset import Asset
from models.key_stats_model import AlertKeyStats
from models.vol_n import TxMetricType

BAR_WIDTH = 514
BAR_HEIGHT = 12


class KeyStatsPictureGenerator(BasePictureGenerator):
    BASE = './data'
    BG_FILE = f'{BASE}/key_weekly_stats_bg.png'

    LABEL_COLOR = '#c6c6c6'

    def __init__(self, loc: BaseLocalization, event: AlertKeyStats):
        super().__init__(loc)
        self.bg = Image.open(self.BG_FILE)
        self.event = event
        self.logos = {}
        self.r = Resources()
        self.btc_logo = None
        self.eth_logo = None
        self.usdt_logo = self.usdc_logo = self.busd_logo = self.rune_logo = None

    FILENAME_PREFIX = 'thorchain_weekly_stats'

    async def prepare(self):
        self.btc_logo, self.eth_logo, self.usdt_logo, self.usdc_logo, self.rune_logo = await asyncio.gather(
            self.r.logo_downloader.get_or_download_logo_cached(BTC_SYMBOL),
            self.r.logo_downloader.get_or_download_logo_cached(ETH_SYMBOL),
            self.r.logo_downloader.get_or_download_logo_cached(ETH_USDT_SYMBOL),
            self.r.logo_downloader.get_or_download_logo_cached(ETH_USDC_SYMBOL),
            self.r.logo_downloader.get_or_download_logo_cached(NATIVE_RUNE_SYMBOL),
        )

        logo_size = int(self.btc_logo.width * 0.25)
        self.btc_logo = self.btc_logo.resize((logo_size, logo_size))
        self.eth_logo = self.eth_logo.resize((logo_size, logo_size))

        usd_logo_size = int(self.btc_logo.width * 0.77)

        self.usdc_logo = self.usdc_logo.resize((usd_logo_size, usd_logo_size))
        self.usdt_logo = self.usdt_logo.resize((usd_logo_size, usd_logo_size))
        self.rune_logo = self.rune_logo.resize((logo_size, logo_size))

    @async_wrap
    def _get_picture_sync(self):
        # prepare data
        r, loc, e = self.r, self.loc, self.event
        curr_lock, prev_lock = e.locked_value_usd_curr_prev

        total_revenue_usd, prev_total_revenue_usd = e.current.earnings.total_earnings, e.previous.earnings.total_earnings
        aff_fee_usd, prev_aff_fee_usd = e.current.earnings.affiliate_revenue, e.previous.earnings.affiliate_revenue

        aff_collectors = e.top_affiliates

        unique_swap, prev_unique_swap = e.current.swapper_count, e.previous.swapper_count

        # prepare painting stuff
        image = self.bg.copy()
        draw = ImageDraw.Draw(image)

        # Week dates
        start_date = self.event.end_date - timedelta(days=self.event.days)
        period_str = self.loc.text_key_stats_period(start_date, self.event.end_date)

        draw.text((1862, 236), period_str,
                  fill='#fff', font=r.fonts.get_font_bold(52),
                  anchor='rm')

        # Block subtitles
        subtitle_font = r.fonts.get_font_bold(40)
        for x, caption in [
            (378, loc.TEXT_PIC_STATS_NATIVE_ASSET_VAULTS),
            (1024, loc.TEXT_PIC_STATS_WEEKLY_REVENUE),
            (2048 - 378, loc.TEXT_PIC_STATS_SWAP_INFO)
        ]:
            draw.text((x, 362),
                      caption, fill=self.LABEL_COLOR, font=subtitle_font,
                      anchor='ms')  # s stands for "Baseline"

        # ----- Block vaults -----

        font_small_n = r.fonts.get_font(34)
        font_indicator_name = r.fonts.get_font(42)

        coin_x = 151
        values = [
            (e.previous.btc_total_amount, e.current.btc_total_amount),
            (e.previous.eth_total_amount, e.current.eth_total_amount),
            (e.previous.usd_total_amount, e.current.usd_total_amount),
        ]
        vaults_y = [473 + i * 116 for i in range(3)]
        postfixes = [' ₿', ' Ξ', 'usd', ]

        paste_image_masked(image, self.btc_logo, (coin_x, vaults_y[0]))
        paste_image_masked(image, self.eth_logo, (coin_x, vaults_y[1]))

        paste_image_masked(image, self.usdt_logo, (coin_x - 20, vaults_y[2]))
        paste_image_masked(image, self.usdc_logo, (coin_x + 20, vaults_y[2]))

        text_x = coin_x + 94
        # draw.text((text_x, vaults_y[3] - 30), 'RUNEPool', fill=self.LABEL_COLOR, font=font_small_n, anchor='ls')

        coin_font = r.fonts.get_font_bold(54)

        for postfix, y, (old_v, new_v) in zip(postfixes, vaults_y, values):
            if postfix == 'usd':
                text = short_dollar(new_v)
            else:
                text = short_money(new_v, postfix=postfix)

            self.text_and_change(old_v, new_v, draw, text_x, y,
                                 text, coin_font, font_small_n)

        # ------- total native asset pooled -------

        y = 918

        self._indicator(draw, 100, y, loc.TEXT_PIC_STATS_NATIVE_ASSET_POOLED,
                        short_dollar(curr_lock.total_non_rune_usd),
                        prev_lock.total_value_pooled_usd, curr_lock.total_non_rune_usd)

        # ------- total network security usd -------
        y += 140

        self._indicator(draw, 100, y, loc.TEXT_PIC_STATS_NETWORK_SECURITY,
                        short_dollar(curr_lock.total_value_bonded_usd),
                        prev_lock.total_value_bonded_usd, curr_lock.total_value_bonded_usd)

        # 2. Block
        # -------- protocol revenue -----

        x = 769

        self._indicator(draw, x, 442,
                        loc.TEXT_PIC_STATS_PROTOCOL_REVENUE,
                        short_dollar(total_revenue_usd),
                        prev_total_revenue_usd, total_revenue_usd)

        self._indicator(draw, x, 623,
                        loc.TEXT_PIC_STATS_AFFILIATE_REVENUE,
                        short_dollar(aff_fee_usd),
                        prev_aff_fee_usd, aff_fee_usd)

        # ----- top 3 affiliates table -----

        draw.text((x, 780),
                  loc.TEXT_PIC_STATS_TOP_AFFILIATE,
                  fill=self.LABEL_COLOR,
                  font=font_indicator_name)

        n_max = 3
        y = 844
        y_margin = 60
        font_aff = r.fonts.get_font_bold(40)
        for i, (label, fee_usd) in zip(range(1, n_max + 1), aff_collectors):
            text = f'{i}. {label}'
            draw.text((x, y),
                      text,
                      font=font_aff,
                      fill='#fff')
            w, _ = font_estimate_size(font_aff, text)

            draw.text((x + w + 20, y + 6),
                      bracketify(short_dollar(fee_usd)),
                      # fill='#afa',
                      fill=COLOR_OF_PROFIT,
                      font=font_small_n)

            y += y_margin

        # ----- organic fees vs block rewards
        #
        # draw.text((x, 1050),
        #           loc.TEXT_PIC_STATS_ORGANIC_VS_BLOCK_REWARDS,
        #           fill=self.LABEL_COLOR,
        #           font=r.fonts.get_font(37))
        #
        # font_fee = r.fonts.get_font_bold(32)
        # x_right = 1283
        #
        # y_p, y_bar = 1142, 1105
        #
        # distribution_bar_chart(
        #     draw,
        #     [liq_fee_usd, block_rewards_usd],
        #     x, y_bar, width=BAR_WIDTH, height=BAR_HEIGHT,
        #     palette=[TC_YGGDRASIL_GREEN, TC_LIGHTNING_BLUE], gap=6
        # )
        #
        # draw.text((x, y_p),
        #           format_percent(organic_ratio, 1, threshold=0.0),
        #           font=font_fee,
        #           anchor='lm',
        #           fill=TC_YGGDRASIL_GREEN)
        #
        # draw.text((x_right, y_p),
        #           format_percent(block_ratio, 1, threshold=0.0),
        #           font=font_fee,
        #           anchor='rm',
        #           fill=TC_LIGHTNING_BLUE)

        # 3. Block

        x, y = 1423, 442

        # ---- unique swappers -----

        self._indicator(draw, x, y,
                        loc.TEXT_PIC_STATS_UNIQUE_SWAPPERS,
                        pretty_money(unique_swap),
                        prev_unique_swap, unique_swap)

        # ---- count of swaps ----

        y += 159
        self._draw_swap_stats_block(draw, x, y)

        # ---- routes ----

        y += 350

        self._draw_routes(draw, n_max, x, y)

        return image

    def _indicator(self, draw, _x, _y, name, text_value, old_value, new_value, _margin=72, under=True):
        font_coin = self.r.fonts.get_font_bold(54)
        font_small_n = self.r.fonts.get_font(34)
        font_indicator_name = self.r.fonts.get_font(42)

        draw.text((_x, _y),
                  name,
                  anchor='lt', fill=self.LABEL_COLOR,
                  font=font_indicator_name)

        if text_value:
            if under:
                x = _x
                y = _y + _margin
                x_shift, y_shift = 20, 6
            else:
                x = _x + _margin
                y = _y
                x_shift, y_shift = 100, 0

            self.text_and_change(
                old_value, new_value,
                draw, x, y,
                text_value,
                font_coin, font_small_n,
                x_shift=x_shift, y_shift=y_shift,
            )

    def _draw_routes(self, draw, n_max, x, y):
        font_small_n = self.r.fonts.get_font(34)
        font_routes = self.r.fonts.get_font_bold(40)
        font_indicator_name = self.r.fonts.get_font(42)

        y_margin = 60

        draw.text((x, y),
                  self.loc.TEXT_PIC_STATS_TOP_SWAP_ROUTES,
                  fill='#fff',
                  font=font_indicator_name)

        y += 60

        swap_routes = self.event.swap_routes
        for i, ((label_left, label_right), count) in zip(range(1, n_max + 1), swap_routes):
            l_asset, r_asset = Asset(label_left), Asset(label_right)

            text = f'{i}. {l_asset.name} ⇌ {r_asset.name}'

            draw.text((x, y),
                      text,
                      font=font_routes,
                      fill='#fff')

            w, _ = font_estimate_size(font_routes, text)

            draw.text((x + w + 20, y + 6),
                      bracketify(short_dollar(count)),
                      fill=COLOR_OF_PROFIT,
                      font=font_small_n)

            y += y_margin

    def get_swap_info_prev_curr(self, metric, is_count):
        attr_name = 'swap_count' if is_count else 'swap_vol'

        prev_total, curr_total = (
            getattr(self.event.previous, attr_name)[metric],
            getattr(self.event.current, attr_name)[metric]
        )

        if metric == TxMetricType.SWAP:
            # we must subtract trade swap metrics from total swaps
            prev_trade, curr_trade = self.get_swap_info_prev_curr(attr_name, TxMetricType.TRADE_SWAP)
            return (
                prev_total - prev_trade,
                curr_total - curr_trade
            )
        else:
            return prev_total, curr_total

    def get_volumes_by_asset_type(self):
        # Little hack to make the sum of the volumes equal to the USD volume.
        # We are not able to record all swap events correctly, but we can extract an approximate distribution.
        # Using this distribution, we calculate the actual trading volumes of different assets.
        total_usd_volume, prev_total_usd_volume = self.event.current.total_volume_usd, self.event.previous.total_volume_usd
        dist = self.event.swap_type_distribution
        n, t = (
            dist.get(TxMetricType.SWAP, 0.0),
            dist.get(TxMetricType.TRADE_SWAP, 0.0),
        )

        curr_vol_normal = total_usd_volume * n
        curr_vol_trade = total_usd_volume * t
        prev_vol_normal = prev_total_usd_volume * n
        prev_vol_trade = prev_total_usd_volume * t

        return (
            (curr_vol_normal, curr_vol_trade),
            (prev_vol_normal, prev_vol_trade),
        )

    def _draw_swap_stats_block(self, draw, x, y):
        loc = self.loc

        # ----- SWAP VOLUME -----

        usd_volume, prev_usd_volume = self.event.usd_volume_curr_prev
        self._indicator(draw, x, y,
                        self.loc.TEXT_PIC_STATS_USD_VOLUME,
                        short_dollar(usd_volume),
                        prev_usd_volume, usd_volume)

        # ----- HORIZONTAL SWAP VOL DISTRIBUTION CHART -----

        y += 150

        (
            (curr_vol_normal, curr_vol_trade),
            (prev_vol_normal, prev_vol_trade),
        ) = self.get_volumes_by_asset_type()

        prev_count_trade, curr_count_trade = self.get_swap_info_prev_curr(TxMetricType.TRADE_SWAP, is_count=True)
        prev_count_normal, curr_count_normal = self.get_swap_info_prev_curr(TxMetricType.SWAP, is_count=True)

        palette = [TC_YGGDRASIL_GREEN, TC_LIGHTNING_BLUE]
        distribution_bar_chart(
            draw,
            # values=[swap_n_normal, swap_n_trade],
            values=[curr_vol_normal, curr_vol_trade],
            x=x, y=y, width=BAR_WIDTH, height=BAR_HEIGHT,
            palette=palette,
            gap=6,
        )

        # ----- CHART LABELS -----

        y += 49

        font = self.r.fonts.get_font_bold(32)

        x_normal = x
        x_trade = x + BAR_WIDTH

        draw.text((x_normal, y), loc.TEXT_PIC_STATS_NORMAL, fill=palette[0], font=font, anchor='ls')
        draw.text((x_trade, y), loc.TEXT_PIC_STATS_TRADE, fill=palette[1], font=font, anchor='rs')

        font_small_n = self.r.fonts.get_font(24)
        coin_font = self.r.fonts.get_font_bold(40)

        # ---- TX COUNTERS ----

        y += 35
        font_tx_count = self.r.fonts.get_font(27)
        draw.text((x_normal, y), f'{short_money(curr_count_normal, integer=True)} txs', font=font_tx_count,
                  anchor='ls',
                  fill=palette[0])
        draw.text((x_trade, y), f'{short_money(curr_count_trade, integer=True)} txs', font=font_tx_count,
                  anchor='rs',
                  fill=palette[1])

        # ---- TX VOLUME FIGURES ----

        y += 44
        draw.text((x_normal, y), short_dollar(curr_vol_normal), font=coin_font, fill=palette[0], anchor='ls')
        draw.text((x_trade, y), short_dollar(curr_vol_trade), font=coin_font, fill=palette[1], anchor='rs')

        # ---- TX VOLUME CHANGE ----

        y += 32
        self.draw_text_change(prev_vol_normal, curr_vol_normal, draw, x_normal, y, font_small_n, anchor='ls')
        self.draw_text_change(prev_vol_trade, curr_vol_trade, draw, x_trade, y, font_small_n, anchor='rs')
