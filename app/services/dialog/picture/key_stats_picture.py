import asyncio
from datetime import timedelta

from PIL import Image, ImageDraw

from localization.manager import BaseLocalization
from services.dialog.picture.common import BasePictureGenerator
from services.dialog.picture.resources import Resources
from services.lib.constants import BTC_SYMBOL, ETH_SYMBOL, ETH_USDC_SYMBOL, ETH_USDT_SYMBOL
from services.lib.draw_utils import paste_image_masked, TC_LIGHTNING_BLUE, TC_YGGDRASIL_GREEN, \
    dual_side_rect, COLOR_OF_PROFIT, font_estimate_size
from services.lib.money import pretty_money, short_dollar, format_percent
from services.lib.texts import bracketify
from services.lib.utils import async_wrap
from services.models.asset import Asset
from services.models.flipside import AlertKeyStats


class KeyStatsPictureGenerator(BasePictureGenerator):
    BASE = './data'
    BG_FILE = f'{BASE}/key_weekly_stats_bg.png'

    def __init__(self, loc: BaseLocalization, event: AlertKeyStats):
        super().__init__(loc)
        self.bg = Image.open(self.BG_FILE)
        self.event = event
        self.logos = {}
        self.r = Resources()
        self.btc_logo = None
        self.eth_logo = None
        self.usdt_logo = self.usdc_logo = self.busd_logo = None

    FILENAME_PREFIX = 'thorchain_weekly_stats'

    async def prepare(self):
        self.btc_logo, self.eth_logo, self.usdt_logo, self.usdc_logo = await asyncio.gather(
            self.r.logo_downloader.get_or_download_logo_cached(BTC_SYMBOL),
            self.r.logo_downloader.get_or_download_logo_cached(ETH_SYMBOL),
            self.r.logo_downloader.get_or_download_logo_cached(ETH_USDT_SYMBOL),
            self.r.logo_downloader.get_or_download_logo_cached(ETH_USDC_SYMBOL),
        )
        logo_size = int(self.btc_logo.width * 0.66)
        self.usdc_logo.thumbnail((logo_size, logo_size))
        self.usdt_logo.thumbnail((logo_size, logo_size))

    @async_wrap
    def _get_picture_sync(self):
        # prepare data
        r, loc, e = self.r, self.loc, self.event
        curr_lock, prev_lock = e.locked_value_usd_curr_prev

        total_revenue_usd, prev_total_revenue_usd = e.total_revenue_usd_curr_prev
        block_rewards_usd, prev_block_rewards_usd = e.block_rewards_usd_curr_prev
        liq_fee_usd, prev_liq_fee_usd = e.liquidity_fee_usd_curr_prev
        aff_fee_usd, prev_aff_fee_usd = e.affiliate_fee_usd_curr_prev

        block_ratio = e.block_ratio
        organic_ratio = e.organic_ratio
        aff_collectors = e.top_affiliate_daily

        swap_count, prev_swap_count = e.swap_count_curr_prev
        usd_volume, prev_usd_volume = e.usd_volume_curr_prev
        unique_swap, prev_unique_swap = e.current.swapper_count, e.previous.swapper_count

        swap_routes = e.swap_routes

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
                      caption, fill='#c6c6c6', font=subtitle_font,
                      anchor='ms')  # s stands for "Baseline"

        # ----- Block vaults -----

        font_small_n = r.fonts.get_font(34)
        font_indicator_name = r.fonts.get_font(42)

        coin_x = 151
        values = [
            (e.get_sum((BTC_SYMBOL,), previous=True), e.get_sum((BTC_SYMBOL,))),
            (e.get_sum((ETH_SYMBOL,), previous=True), e.get_sum((ETH_SYMBOL,))),
            (e.get_stables_sum(previous=True), e.get_stables_sum()),
        ]
        vaults_y = [473, 622, 771]
        postfixes = [' ₿', ' Ξ', 'usd']
        stable_y = vaults_y[2]

        paste_image_masked(image, self.btc_logo, (coin_x, 473))
        paste_image_masked(image, self.eth_logo, (coin_x, 622))

        paste_image_masked(image, self.usdt_logo, (coin_x - 20, stable_y))
        paste_image_masked(image, self.usdc_logo, (coin_x + 20, stable_y))

        coin_font = r.fonts.get_font_bold(54)

        for postfix, y, (old_v, new_v) in zip(postfixes, vaults_y, values):
            if postfix == 'usd':
                text = short_dollar(new_v)
            else:
                text = pretty_money(new_v, postfix=postfix)

            text_x = coin_x + 110

            self.text_and_change(old_v, new_v, draw, text_x, y,
                                 text, coin_font, font_small_n)

        # helper:

        def _indicator(_x, _y, name, text_value, old_value, new_value, _margin=72):
            draw.text((_x, _y),
                      name,
                      anchor='lt', fill='#fff',
                      font=font_indicator_name)

            if text_value:
                self.text_and_change(
                    old_value, new_value,
                    draw, _x, _y + _margin,
                    text_value,
                    coin_font, font_small_n
                )

        # ------- total native asset pooled -------

        margin, delta_y = 78, 160
        y = 888

        _indicator(100, y, loc.TEXT_PIC_STATS_NATIVE_ASSET_POOLED,
                   short_dollar(curr_lock.total_value_pooled_usd),
                   prev_lock.total_value_pooled_usd, curr_lock.total_value_pooled_usd)

        # ------- total network security usd -------

        _indicator(100, y + delta_y, loc.TEXT_PIC_STATS_NETWORK_SECURITY,
                   short_dollar(curr_lock.total_value_bonded_usd),
                   prev_lock.total_value_bonded_usd, curr_lock.total_value_bonded_usd)

        # 2. Block
        # -------- protocol revenue -----

        x = 769

        _indicator(x, 442,
                   loc.TEXT_PIC_STATS_PROTOCOL_REVENUE,
                   short_dollar(total_revenue_usd),
                   prev_total_revenue_usd, total_revenue_usd)

        _indicator(x, 623,
                   loc.TEXT_PIC_STATS_AFFILIATE_REVENUE,
                   short_dollar(aff_fee_usd),
                   prev_aff_fee_usd, aff_fee_usd)

        # ----- top 3 affiliates table -----

        draw.text((x, 780),
                  loc.TEXT_PIC_STATS_TOP_AFFILIATE,
                  fill='#fff',
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

        draw.text((x, 1050),
                  loc.TEXT_PIC_STATS_ORGANIC_VS_BLOCK_REWARDS,
                  fill='#fff',
                  font=r.fonts.get_font(37))

        font_fee = r.fonts.get_font_bold(32)
        x_right = 1283

        y_p, y_bar = 1142, 1105

        dual_side_rect(draw, x, y_bar, x_right, y_bar + 14,
                       liq_fee_usd, block_rewards_usd,
                       TC_YGGDRASIL_GREEN, TC_LIGHTNING_BLUE)

        draw.text((x, y_p),
                  format_percent(organic_ratio, 1, threshold=0.0),
                  font=font_fee,
                  anchor='lm',
                  fill=TC_YGGDRASIL_GREEN)

        draw.text((x_right, y_p),
                  format_percent(block_ratio, 1, threshold=0.0),
                  font=font_fee,
                  anchor='rm',
                  fill=TC_LIGHTNING_BLUE)

        # 3. Block

        x, y = 1423, 442

        # ---- unique swappers -----

        _indicator(x, y,
                   loc.TEXT_PIC_STATS_UNIQUE_SWAPPERS,
                   pretty_money(unique_swap),
                   prev_unique_swap, unique_swap)

        # ---- count of swaps ----

        y += 159

        _indicator(x, y,
                   loc.TEXT_PIC_STATS_NUMBER_OF_SWAPS,
                   pretty_money(swap_count),
                   prev_swap_count, swap_count)

        # ---- swap volume -----

        y += 159

        _indicator(x, y,
                   loc.TEXT_PIC_STATS_USD_VOLUME,
                   short_dollar(usd_volume),
                   prev_usd_volume, usd_volume)

        # ---- routes ----

        y += 159

        draw.text((x, y),
                  loc.TEXT_PIC_STATS_TOP_SWAP_ROUTES,
                  fill='#fff',
                  font=font_indicator_name)

        y += 60
        y_margin = 60

        font_routes = r.fonts.get_font_bold(40)
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

        return image
