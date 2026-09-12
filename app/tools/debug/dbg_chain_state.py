import asyncio
import json
import logging
from pathlib import Path
from typing import Dict

from api.aionode.types import ThorChainInfo
from jobs.fetch.chains import ChainStateFetcher
from lib.texts import sep
from lib.utils import chance_50
from notify.public.chain_notify import TradingHaltedNotifier, AlertChainHalt
from tools.lib.lp_common import LpAppFramework

DEMO_DIR = Path(__file__).parents[2] / 'renderer' / 'demo'


async def show_chain_state_once(app):
    fetcher_chain_state = ChainStateFetcher(app.deps)
    data = await fetcher_chain_state.fetch()
    print(data)
    sep()
    print(app.deps.chain_info.state_list)


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
    fetcher_chain_state.sleep_period = 1
    notifier_trade_halt = TradingHaltedNotifier(d)
    fetcher_chain_state.add_subscriber(notifier_trade_halt)
    notifier_trade_halt.add_subscriber(d.alert_presenter)
    await fetcher_chain_state.run()


async def dbg_chain_halt_infographic_data(app: LpAppFramework):
    """Dump the current network status to renderer/demo/chain_halt.json."""
    data = await ChainStateFetcher(app.deps).fetch()
    table = await TradingHaltedNotifier(app.deps).build_status_table(data)

    output = {
        'template_name': 'chain_halt.jinja2',
        'parameters': table.to_dict(),
    }

    out_path = DEMO_DIR / 'chain_halt.json'
    out_path.write_text(json.dumps(output, indent=2))
    print(f'Written to {out_path}')
    print(json.dumps(output, indent=2))


async def dbg_chain_halt_infographic_send(app: LpAppFramework, chain: str = 'LTC'):
    """Render the network status infographic for a fake halt of the given chain and send it."""
    data = await ChainStateFetcher(app.deps).fetch()

    info = data.get(chain)
    if not info:
        print(f'Chain {chain!r} is unknown. Available: {", ".join(sorted(data.keys()))}')
        return

    # pretend that this very chain has just halted, so it gets highlighted in the picture
    data[chain] = info = info._replace(halted=True, chain_trading_paused=True)
    table = await TradingHaltedNotifier(app.deps).build_status_table(data, [info])

    await app.deps.alert_presenter.handle_data(AlertChainHalt([info], table))
    print('Chain halt infographic sent.')
    await asyncio.sleep(5)  # give some time for the alert to be processed before exiting


async def main():
    app = LpAppFramework(log_level=logging.WARNING)
    async with app:
        # await demo_chain_halt_notifications(app)
        # await dbg_chain_halt_infographic_data(app)
        # await dbg_chain_halt_infographic_send(app)
        await show_chain_state_once(app)


if __name__ == '__main__':
    asyncio.run(main())
