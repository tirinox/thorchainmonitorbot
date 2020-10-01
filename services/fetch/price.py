import logging

ASSET_PRICE_URL = "https://chaosnet-midgard.bepswap.com/v1/assets?asset={asset}"
STABLE_COIN = "BNB.BUSD-BD1"


async def get_prices_of(session, asset_list):
    asset_list = ','.join(asset_list)

    price_url = ASSET_PRICE_URL.format(asset=asset_list)
    logging.info(f"loading prices for {asset_list}...")
    async with session.get(price_url) as resp:
        info = await resp.json()
        return {
            pool['asset']: float(pool["priceRune"]) for pool in info
        }


async def get_price_of(session, asset):
    price_map = await get_prices_of(session, [asset])
    return price_map[asset]
