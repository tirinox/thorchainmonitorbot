import asyncio
import logging
import os.path

import uvicorn
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles

from services.lib.config import Config
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.lib.nop_links import SettingsManager
from services.lib.utils import setup_logs
from services.models.node_watchers import NodeWatcherStorage


class AppSettingsAPI:
    def __init__(self):
        d = self.deps = DepContainer()
        d.cfg = Config()

        self.log_level = d.cfg.get_pure('log_level', logging.INFO)
        setup_logs(self.log_level)

        logging.info(f'Starting Web API for THORChain monitoring bot @ "{d.cfg.network_id}".')

        d.price_holder.load_stable_coins(d.cfg)

        d.loop = asyncio.get_event_loop()
        d.db = DB(d.loop)

        self.web_app = Starlette(
            debug=bool(d.cfg.web.debug),
            routes=self._routes(),
            on_startup=[self._on_startup]
        )
        self.web_app.add_middleware(
            CORSMiddleware,
            allow_origins='*',
            allow_methods='*'
        )

        self.manager = SettingsManager(d.db, d.cfg)

    async def _on_startup(self):
        await self.deps.db.get_redis()
        # print(await self.manager.generate_new_token('test_c'))  # debug

    async def _get_settings(self, request):
        token = request.path_params.get('token')
        channel_id = await self.manager.token_channel_db.get(token)
        if not channel_id:
            return JSONResponse({
                'error': 'channel not found'
            })

        all_nodes = list(await NodeWatcherStorage(self.deps.db, channel_id).all_nodes_for_user())
        settings = await self.manager.get_settings(channel_id)
        return JSONResponse({
            'channel': channel_id,
            'settings': settings,
            'nodes': all_nodes,
        })

    async def _set_settings(self, request):
        token = request.path_params.get('token')
        channel_id = await self.manager.token_channel_db.get(token)
        if not channel_id:
            return JSONResponse({
                'error': 'channel not found'
            })
        data: dict = await request.json()

        nodes_set = False
        if 'nodes' in data:
            nodes = data.pop('nodes')
            storage = NodeWatcherStorage(self.deps.db, channel_id)
            await storage.clear_user_nodes()
            await storage.add_user_to_node_list(nodes)
            nodes_set = True

        settings_set = False
        if 'settings' in data:
            settings = data.pop('settings')
            await self.manager.set_settings(channel_id, settings)
            settings_set = True

        return JSONResponse({
            'channel': channel_id,
            'nodes_set': nodes_set,
            'settings_set': settings_set,
        })

    async def _del_settings(self, request):
        token = request.path_params.get('token')
        channel_id = await self.manager.token_channel_db.get(token)
        if not channel_id:
            return JSONResponse({
                'error': 'channel not found'
            })
        await self.manager.revoke_token(channel_id)
        return JSONResponse({'channel': channel_id, 'status': 'revoked'})

    def _routes(self):
        return [
            Route('/api/settings/{token}', self._get_settings, methods=['GET']),
            Route('/api/settings/{token}', self._set_settings, methods=['POST']),
            Route('/api/settings/{token}', self._del_settings, methods=['DELETE']),
            Mount('/', app=StaticFiles(
                directory=os.path.abspath('./data/web/settings_front_build'),
                html=True,
            ), name="frontend"),
        ]

    def run(self):
        cfg = self.deps.cfg.web
        port = int(cfg.get('port', 8000))
        host = str(cfg.get('host', 'localhost'))
        # reload = bool(cfg.get('reload', False))
        uvicorn.run(
            self.web_app, http='h11',
            loop='asyncio', port=port,
            # reload=reload,
            log_level=self.log_level.lower(),
            host=host
        )


if __name__ == '__main__':
    AppSettingsAPI().run()
