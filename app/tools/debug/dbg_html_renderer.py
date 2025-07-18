import asyncio
import os
import time

from PIL import Image

from jobs.fetch.secured_asset import SecuredAssetAssetFetcher
from lib.html_renderer import InfographicRendererRPC
from lib.texts import sep
from lib.utils import load_pickle, save_pickle
from notify.channel import BoardMessage
from tools.lib.lp_common import LpAppFramework

OUT_FILE = '../temp/renderer_output.png'


async def demo_render_v1(app):
    ig_render = InfographicRendererRPC(app.deps, timeout=60.0)
    png_bytes = await ig_render.render('rune_burn_and_income.jinja2', {
        "title": "Test Render",
        "heading": "Hello, World!",
        "message": "This is a test HTML to PNG rendering.",
        # "width": 800, "height": 600
    })

    if png_bytes:
        print(f"Received PNG image and saved as {OUT_FILE}")
        with open(OUT_FILE, 'wb') as f:
            f.write(png_bytes)
        os.system(f'open "{OUT_FILE}"')

        image = Image.open(OUT_FILE)
        print(f"Image size: {image.size}")

    else:
        print("Failed to render PNG image.")


DEMO_PICKLE = '../temp/secured_asset_data_to_test_render.pickle'


async def demo_render_v2_alert_presenter_benchmark(app):
    secured_asset_info = load_pickle(DEMO_PICKLE)
    if not secured_asset_info:
        f = SecuredAssetAssetFetcher(app.deps)
        secured_asset_info = await f.fetch()
        if f:
            save_pickle(DEMO_PICKLE, secured_asset_info)

    sep("Render")
    elapsed_times = []
    for i in range(5):
        start_time = time.time()
        photo, photo_name = await app.deps.alert_presenter.render_secured_asset_summary(None, secured_asset_info)
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"Rendering {photo_name} took {elapsed_time:.2f} seconds.")
        elapsed_times.append(elapsed_time)

    avg_elapsed_time = sum(elapsed_times) / len(elapsed_times)
    text = f"Rendered secured asset summary in {avg_elapsed_time:.2f} seconds.\n"

    await app.deps.broadcaster.broadcast_to_all(
        BoardMessage.make_photo(photo, caption=text, photo_file_name=photo_name)
    )


async def main():
    app = LpAppFramework()
    async with app:
        # await demo_render_v1(app)
        await demo_render_v2_alert_presenter_benchmark(app)


if __name__ == "__main__":
    LpAppFramework.solve_working_dir_mess()
    asyncio.run(main())
