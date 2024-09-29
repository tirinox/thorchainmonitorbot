import asyncio
import logging
import os.path

import uvicorn
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles

from api.w3.dex_analytics import DexAnalyticsCollector
from comm.slack.slack_bot import SlackBot
from jobs.user_counter import UserCounterMiddleware
from lib.config import Config
from lib.date_utils import parse_timespan_to_seconds, DAY
from lib.db import DB
from lib.depcont import DepContainer
from lib.geo_ip import GeoIPManager
from lib.settings_manager import SettingsManager
from lib.utils import setup_logs, recursive_asdict
from models.node_watchers import NodeWatcherStorage


class AppSettingsAPI:
    IP_MAX_LEN = 2 ** 18

    def __init__(self):
        d = self.deps = DepContainer()
        d.cfg = Config()

        self.log_level = d.cfg.get_pure('log_level', logging.INFO)
        setup_logs(self.log_level)

        logging.info(f'Starting Web API for THORChain monitoring bot @ "{d.cfg.network_id}".')

        d.price_holder.load_stable_coins(d.cfg)

        d.loop = asyncio.get_event_loop()
        d.db = DB(d.loop)

        self._node_watcher = NodeWatcherStorage(d.db)

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

        d.settings_manager = SettingsManager(d.db, d.cfg)
        self.slack = SlackBot(d.cfg, d.db, d.settings_manager)

        self._user_counter = UserCounterMiddleware(d)

    async def _on_startup(self):
        self.deps.make_http_session()
        await self.deps.db.get_redis()

    @property
    def manager(self):
        return self.deps.settings_manager

    async def _get_settings(self, request):
        token = request.path_params.get('token')
        channel_id = await self.manager.token_channel_db.get(token)
        if not channel_id:
            return JSONResponse({
                'error': 'channel not found'
            })

        all_nodes = list(await self._node_watcher.all_nodes_for_user(channel_id))
        settings = await self.manager.get_settings(channel_id)
        return JSONResponse({
            'channel': channel_id,
            'settings': settings,
            'nodes': all_nodes,
        })

    async def _get_node_ip_info(self, request):
        ip_address_list = str(request.path_params.get('ip')).strip()[:self.IP_MAX_LEN].split(',')
        ip_address_list = [ip.strip() for ip in ip_address_list]

        geo_ip = GeoIPManager(self.deps)

        info_list = await asyncio.gather(
            *(geo_ip.get_ip_info_from_cache(ip) for ip in ip_address_list)
        )
        info_dic = {ip: info for ip, info in zip(ip_address_list, info_list)}

        if info_dic:
            return JSONResponse(info_dic)
        else:
            return JSONResponse({
                'error': 'not-found'
            })

    async def _set_settings(self, request):
        token = request.path_params.get('token')
        channel_id = await self.manager.token_channel_db.get(token)
        if not channel_id:
            return JSONResponse({
                'error': 'channel not found'
            }, 404)
        data: dict = await request.json()

        nodes_set = False
        if 'nodes' in data:
            nodes = data.pop('nodes')
            await self._node_watcher.clear_user_nodes(channel_id)
            await self._node_watcher.add_user_to_node_list(channel_id, nodes)
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
            }, 404)
        await self.manager.revoke_token(channel_id)
        return JSONResponse({'channel': channel_id, 'status': 'revoked'})

    async def _slack_handle(self, req: Request):
        return await self.slack.slack_handler.handle(req)

    async def _active_users_handle(self, req: Request):
        stats = await self._user_counter.get_main_stats()
        return JSONResponse(stats._asdict())

    async def _get_dex_aggregator_stats(self, req: Request):
        duration = parse_timespan_to_seconds(req.query_params.get('duration', '1d'))
        if duration > 90 * DAY:
            return JSONResponse({'error': 'Max duration 90 Days'}, 400)

        source = DexAnalyticsCollector(self.deps)
        report = await source.get_analytics(duration)
        return JSONResponse(recursive_asdict(report))

    def _routes(self):
        other = []

        serve_front_end = self.deps.cfg.get_pure('web.serve_front_end', False)
        if serve_front_end:
            other.append(Mount('/', app=StaticFiles(
                directory=os.path.abspath('../web/frontend'),
                html=True,
            ), name="frontend"))

        return [
            Route("/slack/events", endpoint=self._slack_handle, methods=["POST"]),
            Route("/slack/install", endpoint=self._slack_handle, methods=["GET"]),
            Route("/slack/oauth_redirect", endpoint=self._slack_handle, methods=["GET"]),

            Route('/api/settings/{token}', self._get_settings, methods=['GET']),
            Route('/api/settings/{token}', self._set_settings, methods=['POST']),
            Route('/api/settings/{token}', self._del_settings, methods=['DELETE']),
            Route('/api/node/ip/{ip}', self._get_node_ip_info, methods=['GET']),

            Route('/api/stats/users', self._active_users_handle, methods=['GET']),
            Route('/api/stats/dex', self._get_dex_aggregator_stats, methods=['GET']),
            *other,
        ]

    def run(self):
        cfg = self.deps.cfg.web
        port = int(cfg.get('port', 8000))
        host = str(cfg.get('host', 'localhost'))
        # reload = bool(cfg.get('reload', False))
        logging.info(f'THORBot Web API {host}:{port}')
        uvicorn.run(
            self.web_app, http='h11',
            loop='asyncio', port=port,
            # reload=reload,
            log_level=self.log_level.lower(),
            host=host
        )


if __name__ == '__main__':
    AppSettingsAPI().run()
