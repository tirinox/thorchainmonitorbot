import asyncio

from models.mimir_naming import MimirNameRules, MIMIR_DICT_FILENAME
from tools.lib.lp_common import LpAppFramework


async def main():
    lp_app = LpAppFramework()
    async with lp_app:
        pools = await lp_app.deps.pool_cache.get_pools()

        mimir_rules = MimirNameRules()
        mimir_rules.load(MIMIR_DICT_FILENAME)
        mimir_rules.update_asset_names(pools)

        new_words = input('Enter new words to add to mimir naming rules (space separated): ').split()
        if not new_words:
            print('No words to add')
            return

        old_words = set(mimir_rules.known_words)

        mimir_rules.add_words(new_words)

        new_words = set(mimir_rules.known_words) - old_words
        print(f'Added words: {new_words}')

        if input('Save changes to mimir naming rules? [y/N]: ').lower() == 'y':
            mimir_rules.save_to(MIMIR_DICT_FILENAME)
            print('Changes saved')
        else:
            print('Changes discarded')


if __name__ == '__main__':
    asyncio.run(main())
