import asyncio
import logging

from api.aionode.wasm import WasmContract, WasmCodeManager
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


async def main():
    app = LpAppFramework(log_level=logging.DEBUG)
    async with app(brief=True):
        await dbg_query_merge_contract(app)


if __name__ == '__main__':
    asyncio.run(main())
