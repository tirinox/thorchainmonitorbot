from localization.base import BaseLocalization
from services.fetch.fair_price import RuneFairPrice
from services.models.pool_info import PoolInfo, MIDGARD_MULT
from services.models.cap_info import ThorInfo
from services.models.tx import StakeTx, short_asset_name, StakePoolStats
from services.utils import pretty_money, link, short_address, code


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

    def price_change(self, current_price, price_1h, price_24h, price_7d, fair_price):
        return f"Price is {current_price}"  # todo! finish and polish!
