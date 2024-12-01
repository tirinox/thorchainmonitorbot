import asyncio
import os

from PIL import Image

from lib.html_renderer import InfographicRendererRPC
from tools.lib.lp_common import LpAppFramework

OUT_FILE = '../temp/renderer_output.png'


async def main():
    app = LpAppFramework()
    async with app(brief=True):
        ig_render = InfographicRendererRPC(app.deps.session, timeout=60.0)
        png_bytes = await ig_render.render('foo.jinja2', {
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


if __name__ == "__main__":
    LpAppFramework.solve_working_dir_mess()
    asyncio.run(main())
