import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, APIRouter
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

from dashboard.context import DashboardContext
from dashboard.routes import overview, jobs, logs, flags

URL_PREFIX = '/dashboard'  # nginx serves the dashboard under this prefix
CSRF_HEADER = 'x-dashboard-request'
SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}

DEFAULT_STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../web/dashboard/dist'))


class StripPrefixMiddleware:
    """Lets the app work both behind nginx (prefix stripped) and directly at http://host:port/dashboard/."""

    def __init__(self, app, prefix: str):
        self.app = app
        self.prefix = prefix

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            path = scope['path']
            if path == self.prefix or path.startswith(self.prefix + '/'):
                scope = dict(scope, path=path[len(self.prefix):] or '/')
        await self.app(scope, receive, send)


class CSRFGuardMiddleware:
    """
    The dashboard is protected by HTTP basic auth, which browsers attach to cross-site requests too.
    Requiring a custom header on mutating requests forces a CORS preflight, which we never allow.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http' and scope['method'] not in SAFE_METHODS and scope['path'].startswith('/api/'):
            headers = dict(scope['headers'])
            if headers.get(CSRF_HEADER.encode()) != b'1':
                response = JSONResponse({'detail': f'Missing {CSRF_HEADER} header'}, status_code=403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


class SPAStaticFiles(StaticFiles):
    """Serves index.html for unknown paths so client-side routes survive a page reload."""

    async def get_response(self, path, scope):
        if path == 'api' or path.startswith('api/'):
            raise StarletteHTTPException(404)
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as e:
            if e.status_code != 404:
                raise
            response = await super().get_response('index.html', scope)
        if path in ('', '.', 'index.html') or response.media_type == 'text/html':
            response.headers['Cache-Control'] = 'no-store'
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ctx = await DashboardContext.create()
    try:
        yield
    finally:
        await app.state.ctx.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title='THORChain Monitor Bot Dashboard',
        lifespan=lifespan,
        docs_url='/api/docs',
        openapi_url='/api/openapi.json',
        redoc_url=None,
    )

    api = APIRouter(prefix='/api')
    for module in (overview, jobs, logs, flags):
        api.include_router(module.router)
    app.include_router(api)

    static_dir = os.environ.get('DASHBOARD_STATIC_DIR', DEFAULT_STATIC_DIR)
    if os.path.isdir(static_dir):
        app.mount('/', SPAStaticFiles(directory=static_dir, html=True), name='spa')
    else:
        logging.warning(f'Dashboard frontend build not found at {static_dir!r}; serving API only.')

    # outermost first: strip prefix, then check CSRF on the normalized path
    app.add_middleware(CSRFGuardMiddleware)
    app.add_middleware(StripPrefixMiddleware, prefix=URL_PREFIX)
    return app
