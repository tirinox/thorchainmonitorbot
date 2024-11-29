import os

from aiohttp import web

# HTTP Server Configuration
HTTP_SERVER_HOST = '127.0.0.1'
HTTP_SERVER_PORT = 8000  # Internal port


class HTTPLocalServer:
    def __init__(self, static_dir=None, host=HTTP_SERVER_HOST, port=HTTP_SERVER_PORT):
        self.static_dir = static_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
        self.host = host
        self.port = port
        self.http_runner = None

    async def handle_static(self, request):
        p = os.path.join(self.static_dir, request.match_info['filename'])
        return web.FileResponse(str(p))

    async def start_http_server(self):
        if self.http_runner:
            return self.http_runner

        app = web.Application()
        app.router.add_get('/static/{filename}', self.handle_static)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, HTTP_SERVER_HOST, HTTP_SERVER_PORT)
        await site.start()
        print(f"HTTP server started at http://{HTTP_SERVER_HOST}:{HTTP_SERVER_PORT}/static/")
        self.http_runner = runner
        return runner

    async def close_http_server(self):
        if self.http_runner:
            await self.http_runner.cleanup()
            print("HTTP server closed.")

    def modify_hrefs(self, html: str):
        return html.replace(
            'href="',
            f'href="http://{self.host}:{self.port}/static/'
        )
