import asyncio
import logging

from api.aionode.wasm import WasmContract, WasmCodeManager
from jobs.fetch.ruji_merge import MergeContract, RujiMergeStatsFetcher
from lib.date_utils import now_ts
from lib.texts import sep
from tools.lib.lp_common import LpAppFramework


async def dbg_query_merge_contract(app):
    thor = app.deps.thor_connector

    code_man = WasmCodeManager(thor)
    code_infos = await code_man.get_code_list()
    print(code_infos)

    code_contracts = await code_man.get_contract_of_code_id(code_infos['code_infos'][0]['code_id'])
    print(code_contracts)

    contract = WasmContract(thor, "thor1yw4xvtc43me9scqfr2jr2gzvcxd3a9y4eq7gaukreugw2yd2f8tsz3392y")

    config = await contract.query_contract({"config": {}})
    print(f"Config: {config}")

    status = await contract.query_contract({"status": {}})
    print(f"Status: {status}")

    sep()

    merge_contract = MergeContract(thor, contract.contract_address)
    config = await merge_contract.load_config()
    print(f"Config: {config}")
    status = await merge_contract.load_status()
    print(f"Status: {status}")


async def dbg_merge_program(app):
    f = RujiMergeStatsFetcher(app.deps)
    system = await f.fetch()
    print(system)
    sep()
    print(f'All denoms are {system.all_denoms}')

    for d in system.all_denoms:
        config, _ = system.find_config_and_status_by_denom(d)
        print(f"{d}: merge_ratio = {config.merge_ratio(now_ts())}")


async def main():
    app = LpAppFramework(log_level=logging.DEBUG)
    async with app:
        # await dbg_query_merge_contract(app)
        await dbg_merge_program(app)


if __name__ == '__main__':
    asyncio.run(main())
