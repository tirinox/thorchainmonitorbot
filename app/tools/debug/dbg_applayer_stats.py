import asyncio
import logging
import time

from jobs.fetch.cached.wasm import WasmCache
from lib.texts import sep
from tools.lib.lp_common import LpAppFramework


async def dbg_wasm_cache(app: LpAppFramework):
    """Cold-load the WASM cache and print a full report."""
    wasm_cache = WasmCache(app.deps.thor_connector, db=app.deps.db)

    sep()
    print(">>> First get() — may come from Redis or network…")
    t0 = time.perf_counter()
    stats = await wasm_cache.get()
    elapsed = time.perf_counter() - t0

    sep()
    print(f"Fetched in {elapsed:.2f}s")
    print(f"Total code variants     : {stats.total_codes}")
    print(f"Total contract instances: {stats.total_contracts}")
    sep()

    for cs in stats.codes:
        print(
            f"  code_id={cs.code_id:>4}  contracts={cs.contract_count:>5}"
            f"  creator={cs.creator[:20]}..."
            f"  hash={cs.data_hash[:12]}..."
        )

async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app:
        await dbg_wasm_cache(app)


if __name__ == '__main__':
    asyncio.run(main())
