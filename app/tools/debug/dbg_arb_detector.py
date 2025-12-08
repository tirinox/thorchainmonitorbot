import asyncio

from jobs.scanner.arb_detector import ArbBotDetector
from tools.lib.lp_common import LpAppFramework


async def arb_detector_1(app: LpAppFramework, address: str):
    arb = ArbBotDetector(app.deps)

    r = await arb.try_to_detect_arb_bot(address)
    info = await app.deps.name_service.lookup_name_by_address(address)
    name = info.name if info else 'NO_NAME'

    print(f"Address: {address}, is_arb: {r}, name: {name}")


async def demo_arb_detector(app: LpAppFramework):
    # definitely be arb
    await arb_detector_1(app, 'thor1ukwhpglu7yh2g2rw8h7jvee2r0fv0e90nyxv6v')

    # not arb
    await arb_detector_1(app, 'thor1e9hjelkhpyd8vm7yf7w6xhgwtlhch5fvq0wp80')

    # binance: many txs, but no swaps
    await arb_detector_1(app, 'thor1t60f02r8jvzjrhtnjgfj4ne6rs5wjnejwmj7fh')



async def run():
    app = LpAppFramework()
    async with app:
        await demo_arb_detector(app)


if __name__ == '__main__':
    asyncio.run(run())
