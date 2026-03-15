import asyncio
import logging
import time

from jobs.fetch.cached.wasm import WasmCache
from lib.texts import sep
from tools.lib.lp_common import LpAppFramework


async def dbg_wasm_cache(app: LpAppFramework):
    """Load the WASM cache and print a full report including contract labels."""
    wasm_cache = WasmCache(app.deps.thor_connector, db=app.deps.db)

    sep()
    print(">>> First get() — may come from Redis or network...")
    t0 = time.perf_counter()
    stats = await wasm_cache.get()
    elapsed = time.perf_counter() - t0

    sep()
    print(f"Fetched in {elapsed:.2f}s")
    print(f"Total code variants     : {stats.total_codes}")
    print(f"Total contract instances: {stats.total_contracts}")

    for cs in stats.codes:
        sep()
        print(
            f"  code_id={cs.code_id:>4}  contracts={cs.contract_count:>5}"
            f"  creator={cs.creator[:20]}..."
            f"  hash={cs.data_hash[:12]}..."
        )
        for entry in cs.contracts:
            print(f"    {entry.address}  label={entry.label!r}")

    sep()
    print(">>> Redis TTL check...")
    r = await app.deps.db.get_redis()
    ttl = await r.ttl(WasmCache.REDIS_KEY)
    if ttl == -2:
        print("  Key not found in Redis.")
    elif ttl == -1:
        print("  Key exists in Redis but has no TTL (unexpected).")
    else:
        print(f"  Key '{WasmCache.REDIS_KEY}' TTL = {ttl}s "
              f"(~{ttl // 3600}h {(ttl % 3600) // 60}m remaining).")

    n_labels = await r.hlen(WasmCache.REDIS_LABELS_HASH)
    print(f"  Labels hash '{WasmCache.REDIS_LABELS_HASH}': {n_labels} entry(ies), no TTL.")

    sep()
    print(">>> get_label() convenience lookup...")
    if stats.all_contracts:
        addr = stats.all_contracts[0].address
        label = await wasm_cache.get_label(addr)
        print(f"  get_label({addr!r}) = {label!r}")

        # test Redis-only path: clear in-memory cache
        wasm_cache._cache = None
        label2 = await wasm_cache.get_label(addr)
        print(f"  (no in-memory cache) get_label({addr!r}) = {label2!r}  [from Redis hash]")
    else:
        print("  (no contracts loaded)")


async def main():
    app = LpAppFramework(log_level=logging.DEBUG)
    async with app:
        await dbg_wasm_cache(app)


if __name__ == '__main__':
    asyncio.run(main())
