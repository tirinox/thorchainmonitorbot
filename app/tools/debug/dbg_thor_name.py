import asyncio

from localization.languages import Language
from services.lib.midgard.name_service import NameService
from services.lib.texts import sep
from services.models.transfer import RuneTransfer
from tools.lib.lp_common import LpAppFramework

NAMES = {
    'panda': 'thor1t3mkwu79rftp4uqf3xrpf5qwczp97jg9jul53p',
    'vitalik': 'thor1e5qhhm93j380xksqpamh74mva2ee6c3wmmrrz4'
}


async def t_names1(lp_app: LpAppFramework):
    ns = lp_app.deps.name_service
    n = await ns.lookup_name_by_address('thor17gw75axcnr8747pkanye45pnrwk7p9c3cqncsv')
    print(n)

    n = await ns.lookup_name_by_address('thorNONAME')
    assert n is None

    n = await ns.lookup_address_by_name('Binance Hot')
    assert n.startswith('thor')
    print(n)


async def t_exists(ns: NameService):
    # r = await ns.safely_load_thornames_from_address_set([NAMES['vitalik']])
    # print(r)
    # r1 = await ns.lookup_name_by_address('thor1e5qhhm93j380xksqpamh74mva2ee6c3wmmrrz4')
    # print(r1)
    r = await ns.lookup_thorname_by_name('panda', forced=True)
    print(r)
    r = await ns.lookup_thorname_by_name('vitalik')
    print(r)


async def t_not_exists(ns: NameService):
    # r = await ns.safely_load_thornames_from_address_set(['fljlfjwljweobo', 'lkelejljjwejlweqq'])
    # print(r)

    r1 = await ns.lookup_name_by_address('thorNOADDRESS')
    print(r1)


async def t_fix_name_map(ns: NameService):
    # thor_swap = await ns.lookup_thorname_by_name('t')
    # print(thor_swap)
    # return

    result = await ns.safely_load_thornames_from_address_set([
        'thor1tcet6mxe80x89a8dlpynehlj4ya7cae4v3hmce',
        'thor136askulc04d0ek9yra6860vsaaamequv2l0jwh',
        'thor13tqs4dgvjyhukx2aed78lu6gz49t6penjwnd50',
        'thor160yye65pf9rzwrgqmtgav69n6zlsyfpgm9a7xk',  # (t)
    ])
    sep('By name')
    print(result.by_name)
    sep('By address')
    print(result.by_address)


async def demo_node_names(app: LpAppFramework):
    await app.deps.node_info_fetcher.run_once()
    nodes = app.deps.node_holder.nodes
    print(f"Total nodes: {len(nodes)}")

    addresses = [
        'thor1hxcdgn43pyz58ajdqd0hl3rfl3avwdd5y27whf',  # bp
        'thor1puhn8fclwvmmzh7uj7546wnxz5h3zar8adtqp3',  # bp
        'thor160yye65pf9rzwrgqmtgav69n6zlsyfpgm9a7xk',  # not a node (but "t")
        'thor166n4w5039meulfa3p6ydg60ve6ueac7tlt0jws',  # has no name
    ]

    name_map = await app.deps.name_service.safely_load_thornames_from_address_set(addresses)
    print(f"Name map is {name_map}")

    # ------------------------------------

    tr = RuneTransfer(
        'thor1puhn8fclwvmmzh7uj7546wnxz5h3zar8adtqp3', 'thor166n4w5039meulfa3p6ydg60ve6ueac7tlt0jws',
        13_123_132, '123456789054321123456789098754321', 222_854.24, 5.29, is_native=True, asset='THOR.RUNE',
        comment='SEND', memo='Hello'
    )

    locs = [
        app.deps.loc_man.default,
        app.deps.loc_man[Language.ENGLISH_TWITTER]
    ]

    for loc in locs:
        sep()
        print(loc.notification_text_rune_transfer_public(tr, name_map))


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        ns = app.deps.name_service
        # await t_exists(ns)
        # await t_not_exists(ns)
        # await t_fix_name_map(ns)
        await demo_node_names(app)


if __name__ == '__main__':
    asyncio.run(run())
