import asyncio
import logging

from services.lib.texts import sep
from services.models.mimir_naming import TRANSLATE_MIMIRS, try_deducting_mimir_name
from tools.lib.lp_common import LpAppFramework


async def main():
    # print(try_to_decompose_mimir_name('MAXNODETOCHURNOUTSUCKFORLOWVERSIONGGG'))
    # print(try_to_decompose_mimir_name('CLOCKANDDAGGER'))
    # print(try_to_decompose_mimir_name('THORCHAINISTHEBESTCHAIN'))
    # print(try_to_decompose_mimir_name('LPPROVIDERUSDSLASHMINDELAYPERIOD'))

    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app:

        described_names = set([k.upper() for k in TRANSLATE_MIMIRS.keys()])
        current_names = set([k.upper() for k in lp_app.deps.mimir_const_holder.all_names])

        for name in described_names:
            print(f'{name} => {try_deducting_mimir_name(name)}')

        sep()

        need_description = current_names - described_names
        need_deletion = described_names - current_names

        sep()
        for name in need_description:
            print(f'Please describe "{name}"')
        print(f'Total to do: {len(need_description)}')

        sep()
        for name in need_deletion:
            print(f'Please remove "{name}"')
        print(f'Total to do: {len(need_deletion)}')

        sep()
        code_gen = ''
        for name in need_description:
            pretty_name = try_deducting_mimir_name(name)
            code_gen += f'    {name.upper()}: {pretty_name},\n'

        print(code_gen)


if __name__ == '__main__':
    asyncio.run(main())
