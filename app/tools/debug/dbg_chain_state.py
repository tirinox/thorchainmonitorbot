import asyncio
import logging
from typing import Dict

from api.aionode.types import ThorChainInfo
from jobs.fetch.chains import ChainStateFetcher
from lib.texts import sep
from lib.utils import chance_50
from notify.public.chain_notify import TradingHaltedNotifier
from tools.lib.lp_common import LpAppFramework


async def show_chain_state_once(app):
    fetcher_chain_state = ChainStateFetcher(app.deps)
    data = await fetcher_chain_state.fetch()
    print(data)


class NaughtyChainStateFetcher(ChainStateFetcher):
    async def fetch(self) -> Dict[str, ThorChainInfo]:
        print('Tick!')
        all_data = await super().fetch()
        avax = all_data.get('AVAX')
        if avax:
            # rewrite with replace
            avax = avax._replace(
                halted=chance_50(),
                global_trading_paused=chance_50(),
                chain_trading_paused=chance_50(),
                chain_lp_actions_paused=chance_50()
            )

            sep()
            print(avax)
            all_data['AVAX'] = avax

        return all_data


async def demo_chain_halt_notifications(app):
    d = app.deps
    fetcher_chain_state = NaughtyChainStateFetcher(d)
    notifier_trade_halt = TradingHaltedNotifier(d)
    fetcher_chain_state.add_subscriber(notifier_trade_halt)
    notifier_trade_halt.add_subscriber(d.alert_presenter)
    await fetcher_chain_state.run()


async def main():
    app = LpAppFramework(log_level=logging.WARNING)
    async with app(brief=True):
        await demo_chain_halt_notifications(app)


if __name__ == '__main__':
    asyncio.run(main())
