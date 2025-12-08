import asyncio
import logging

from lib.settings_manager import SettingsManager
from lib.texts import sep
from lib.utils import safe_get, grouper
from notify.personal.bond_provider import BondWatchlist
from notify.personal.helpers import GeneralSettings
from tools.lib.lp_common import LpAppFramework


async def get_bond_provider_set_true_candidates(app: LpAppFramework, n=100):
    sett_mann: SettingsManager = app.deps.settings_manager
    keys = await sett_mann.all_users_having_settings()

    candidates = []

    for batch in grouper(n, keys):
        all_settings = await sett_mann.get_settings_multi(batch)
        for used_id, settings in all_settings.items():
            if GeneralSettings.BALANCE_TRACK in settings:
                tracked_addresses = safe_get(settings, GeneralSettings.BALANCE_TRACK, 'addresses')

                for address, content in tracked_addresses.items():
                    track_bond = content.get('bond_prov', True)
                    if track_bond:
                        candidates.append((used_id, address))
    return candidates


async def fix_bond_provider_off(app: LpAppFramework):
    candidates = await get_bond_provider_set_true_candidates(app)
    sep('Candidates')
    for index, c in enumerate(candidates, start=1):
        print(f'{index:3d}. {c[0]} | {c[1]}')
    print(f'Total candidates: {len(candidates)}')

    if input('Continue? [y/n]') != 'y':
        return

    bond_provider_watch = BondWatchlist(app.deps.db)
    for used_id, address in candidates:
        await bond_provider_watch.set_user_to_node(used_id, address, True)

    sep('Done')


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app:
        await fix_bond_provider_off(app)


if __name__ == '__main__':
    asyncio.run(main())
