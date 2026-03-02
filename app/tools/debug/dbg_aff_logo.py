import asyncio
import json

from api.midgard.name_service import NameService
from tools.lib.lp_common import LpAppFramework

DEMO_AFF_LOGO_FILENAME = "./renderer/demo/dbg_aff_logo.json"


async def dbg_dump_logo(app: LpAppFramework):
    ns: NameService = app.deps.name_service
    with open(DEMO_AFF_LOGO_FILENAME, "w") as f:
        json.dump({
            "template_name": "dbg_aff_logo.jinja2",
            "parameters": {
                "_width": 1280,
                "_height": 920,
                # "name_to_logo": ns.aff_man.name_to_logo,
                # "thorname_to_name": ns.aff_man.thorname_to_name,
                "affiliate_logos": list(ns.aff_man.name_to_logo.values()),
                "affiliate_names": list(ns.aff_man.name_to_logo.keys()),
            },
        }, f, indent=2)


async def dbg_check_logo_and_names(app: LpAppFramework):
    ns: NameService = app.deps.name_service
    aff = ns.aff_man

    print(f"{'CODE':<40} {'NAME':<30} {'LOGO'}")
    print("-" * 120)

    all_codes = sorted(aff.thorname_to_name.keys())
    for code in all_codes:
        name = aff.get_affiliate_name(code)
        logo = aff.get_affiliate_logo(code, with_local_prefix=True)
        missing = " *** MISSING LOGO ***" if not logo else ""
        print(f"{code:<40} {name:<30} {logo or '(empty)'}{missing}")


async def main():
    app = LpAppFramework()
    async with app:
        await dbg_check_logo_and_names(app)


if __name__ == '__main__':
    asyncio.run(main())
