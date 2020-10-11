import datetime
import logging

from localization.base import BaseLocalization, pretty_money, link, short_address
from services.fetch.price import PoolInfo, RuneFairPrice
from services.models.cap_info import ThorInfo
from services.models.tx import StakeTx, short_asset_name, StakePoolStats


class EnglishLocalization(BaseLocalization):
    # ---- WELCOME ----
    def help(self):
        return f"This bot is for {link('https://thorchain.org/', 'THORChain')} monitoring.\n" \
               f"Command list:\n" \
               f"/help – this help page\n" \
               f"/start – start and set your language\n" \
               f"/cap – the current staking cap of Chaosnet\n" \
               f"/price – the current Rune price.\n" \
               f"<b>⚠️ All notifications are forwarded to️ @thorchain_alert channel!</b>"

    def welcome_message(self, info: ThorInfo):
        return f"Hello! <b>{info.stacked:.0f}</b> coins of <b>{info.cap:.0f}</b> are currently staked.\n" \
               f"The $RUNE price is <code>{info.price:.3f} BUSD</code> now.\n" \
               f"<b>⚠️ All notifications are forwarded to️ @thorchain_alert channel!</b>\n" \
               f"Type /help to see the command list."

    # ----- CAP ------
    def notification_cap_change_text(self, old: ThorInfo, new: ThorInfo):
        verb = "has been increased" if old.cap < new.cap else "has been decreased"
        call = "Come on, go staking!\n" if new.cap > old.cap else ''
        message = f'<b>Cap {verb} from {old.cap:.0f} to {new.cap:.0f}!</b>\n' \
                  f'Currently <b>{new.stacked:.0f}</b> $RUNE are staked.\n' \
                  f'The price of $RUNE in the pool is <code>{new.price:.3f} BUSD</code>.\n' \
                  f'{call}' \
                  f'https://chaosnet.bepswap.com/'
        return message

    # ------ PRICE -------
    def price_message(self, info: ThorInfo, fair_price: RuneFairPrice):
        return f"Last real price of ᚱune is <code>${info.price:.3f}</code>.\n" \
               f"Deterministic price of ᚱune is <code>${fair_price.fair_price:.3f}</code>."

    # ------ TXS -------
    def tx_text(self, tx: StakeTx, rune_per_dollar: float, pool: StakePoolStats, pool_info: PoolInfo):
        msg = ''
        if tx.type == 'stake':
            msg += f'🐳 <b>Whale added liquidity</b> 🟢\n'
        elif tx.type == 'unstake':
            msg += f'🐳 <b>Whale removed liquidity</b> 🔴\n'

        rp, ap = tx.symmetry_rune_vs_asset()
        msg += f"<b>{pretty_money(tx.rune_amount)} ᚱune</b> ({rp:.0f}%) ↔️ " \
               f"<b>{pretty_money(tx.asset_amount)} {short_asset_name(tx.pool)}</b> ({ap:.0f}%)\n"

        total_usd_volume = tx.full_rune / rune_per_dollar if rune_per_dollar != 0 else 0.0
        msg += f"Total: <code>${pretty_money(total_usd_volume)}</code>\n"

        pool_depth_usd = pool_info.rune_depth / rune_per_dollar
        msg += f"Pool depth is <b>${pretty_money(pool_depth_usd)}</b> now.\n"

        info = link(f'https://viewblock.io/thorchain/address/{tx.address}', short_address(tx.address))
        msg += f"Explorer: {info}"

        return msg
