from localization.base import BaseLocalization
from services.models.price import RuneFairPrice, PriceReport
from services.models.pool_info import PoolInfo
from services.models.cap_info import ThorInfo
from services.models.tx import StakeTx, short_asset_name, StakePoolStats
from services.lib.utils import link, code, bold, pre, x_ses
from services.lib.money import pretty_dollar, pretty_money, short_address, adaptive_round_to_str, calc_percent_change, \
    emoji_for_percent_change


class EnglishLocalization(BaseLocalization):
    # ---- WELCOME ----
    def help(self):
        return (
            f"This bot is for {link('https://thorchain.org/', 'THORChain')} monitoring.\n"
            f"Command list:\n"
            f"/help – this help page\n"
            f"/start – start and set your language\n"
            f"/cap – the current staking cap of Chaosnet\n"
            f"/price – the current Rune price.\n"
            f"<b>⚠️ All notifications are forwarded to️ @thorchain_alert channel!</b>"
        )

    def welcome_message(self, info: ThorInfo):
        return (
            f"Hello! <b>{pretty_money(info.stacked)} {self.R}</b> of <b>{pretty_money(info.cap)} {self.R}</b> pooled.\n"
            f"{self._cap_pb(info)}"
            f"The {self.R} price is <code>{info.price:.3f} BUSD</code> now.\n"
            f"<b>⚠️ All notifications are forwarded to️ @thorchain_alert channel!</b>\n"
            f"Type /help to see the command list."
        )

    def unknown_command(self):
        return (
            "Sorry, I didn't understand that command.\n"
            "/help"
        )

    # ----- CAP ------
    def notification_cap_change_text(self, old: ThorInfo, new: ThorInfo):
        verb = "has been increased" if old.cap < new.cap else "has been decreased"
        call = "Come on, add more liquidity!\n" if new.cap > old.cap else ''
        message = (
            f'<b>Pool cap {verb} from {pretty_money(old.cap)} to {pretty_money(new.cap)}!</b>\n'
            f'Currently <b>{pretty_money(new.stacked)}</b> {self.R} are in the liquidity pools.\n'
            f"{self._cap_pb(new)}"
            f'The price of {self.R} in the pool is <code>{new.price:.3f} BUSD</code>.\n'
            f'{call}'
            f'https://chaosnet.bepswap.com/'
        )
        return message

    # ------ PRICE -------
    def price_message(self, info: ThorInfo, fair_price: RuneFairPrice):
        return (
            f"Last real price of {self.R} is <code>${info.price:.3f}</code>.\n"
            f"Deterministic price of {self.R} is <code>${fair_price.fair_price:.3f}</code>."
        )

    # ------ TXS -------
    def tx_text(self, tx: StakeTx, dollar_per_rune: float, pool: StakePoolStats, pool_info: PoolInfo):
        msg = ''
        if tx.type == 'stake':
            msg += f'🐳 <b>Whale added liquidity</b> 🟢\n'
        elif tx.type == 'unstake':
            msg += f'🐳 <b>Whale removed liquidity</b> 🔴\n'

        total_usd_volume = tx.full_rune * dollar_per_rune if dollar_per_rune != 0 else 0.0
        pool_depth_usd = pool_info.usd_depth(dollar_per_rune)
        info = link(f'https://viewblock.io/thorchain/address/{tx.address}', short_address(tx.address))

        rp, ap = tx.symmetry_rune_vs_asset()
        msg += (
            f"<b>{pretty_money(tx.rune_amount)} {self.R}</b> ({rp:.0f}%) ↔️ "
            f"<b>{pretty_money(tx.asset_amount)} {short_asset_name(tx.pool)}</b> ({ap:.0f}%)\n"
            f"Total: <code>${pretty_money(total_usd_volume)}</code>\n"
            f"Pool depth is <b>${pretty_money(pool_depth_usd)}</b> now.\n"
            f"Explorer: {info}"
        )

        return msg

    # ------- QUEUE -------

    def queue_update(self, item_type, step, value):
        if step == 0:
            return f"☺️ Queue {code(item_type)} is empty again!"
        else:
            return (
                f"🤬 <b>Attention!</b> Queue {code(item_type)} has {value} transactions!\n"
                f"{code(item_type)} transactions may be delayed."
            )

    # ------- PRICE -------

    def price_change(self, p: PriceReport, ath=False):
        title = bold('Price update') if not ath else bold('🚀 A new all-time high has been achieved!')

        c_gecko_url = 'https://www.coingecko.com/en/coins/thorchain'
        c_gecko_link = link(c_gecko_url, 'RUNE')

        message = f"{title} | {c_gecko_link}\n"
        price = p.fair_price.real_rune_price

        pr_text = pretty_dollar(price)
        message += f"RUNE price is {code(pr_text)} now.\n"

        time_combos = zip(
            ('1h', '24h', '7d'),
            (p.price_1h, p.price_24h, p.price_7d)
        )
        for title, old_price in time_combos:
            if old_price:
                pc = calc_percent_change(old_price, price)
                message += pre(f"{title.rjust(4)}:{adaptive_round_to_str(pc, True).rjust(8)} % "
                               f"{emoji_for_percent_change(pc).ljust(4).rjust(6)}") + "\n"

        fp = p.fair_price
        if fp.rank >= 1:
            message += f"Coin market cap is {bold(pretty_dollar(fp.market_cap))} (#{bold(fp.rank)})\n"

        if fp.tlv_usd >= 1:
            det_link = link('https://docs.thorchain.org/how-it-works/incentive-pendulum', 'deterministic price')
            message += (f"TVL of non-RUNE assets: ${pre(pretty_money(fp.tlv_usd))}\n"
                        f"So {det_link} of RUNE is {code(pretty_money(fp.fair_price, prefix='$'))}\n"
                        f"Speculative multiplier is {pre(x_ses(fp.fair_price, price))}\n")

        return message.rstrip()
