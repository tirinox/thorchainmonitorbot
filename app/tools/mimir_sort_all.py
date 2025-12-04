import asyncio

from models.mimir_naming import MimirNameRules, MIMIR_DICT_FILENAME
from tools.lib.lp_common import LpAppFramework


def recursive_sort(data):
    if isinstance(data, dict):
        return {key: recursive_sort(data[key]) for key in sorted(data.keys())}
    elif isinstance(data, list):
        return sorted((recursive_sort(item) for item in data), key=str)
    else:
        return data


async def main():
    lp_app = LpAppFramework()
    async with lp_app:
        mimir_rules = MimirNameRules()
        mimir_rules.load(MIMIR_DICT_FILENAME)
        mimir_rules.rules = recursive_sort(mimir_rules.rules)
        mimir_rules.make_words_proper()
        # mimir_rules.save_to(MIMIR_DICT_FILENAME + '.foo.yaml')

        if input('Save changes to mimir naming rules? [y/N]: ').lower() == 'y':
            mimir_rules.save_to(MIMIR_DICT_FILENAME)
            print('Changes saved')
        else:
            print('Changes discarded')


if __name__ == '__main__':
    asyncio.run(main())
