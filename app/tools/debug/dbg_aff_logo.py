import asyncio
import json

from api.midgard.name_service import NameService
from tools.lib.lp_common import LpAppFramework

DEMO_AFF_LOGO_FILENAME = "./renderer/demo/dbg_aff_logo.json"


async def main():
    app = LpAppFramework()
    async with app:
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


if __name__ == '__main__':
    asyncio.run(main())
