import argparse
import logging
import sys

import uvicorn

from lib.config import Config


def main():
    parser = argparse.ArgumentParser(description='Bot admin dashboard (API + web UI)')
    parser.add_argument('config', nargs='?', help='Path to config.yaml (optional)')
    parser.add_argument('--reload', action='store_true', help='Auto-reload on code changes (development)')
    parser.add_argument('--host', help='Overrides dashboard.host from the config')
    parser.add_argument('--port', type=int, help='Overrides dashboard.port from the config')
    args = parser.parse_args()

    # Config() reads the config path from sys.argv[1], so leave only that one there
    sys.argv = [sys.argv[0]] + ([args.config] if args.config else [])

    cfg = Config()
    host = args.host or cfg.as_str('dashboard.host', '0.0.0.0')
    port = args.port or cfg.as_int('dashboard.port', 8501)
    logging.info(f'Bot dashboard at {host}:{port}')

    uvicorn.run(
        'dashboard.server:create_app',
        factory=True,
        host=host,
        port=port,
        loop='asyncio',
        http='h11',
        reload=args.reload,
        reload_dirs=['.'] if args.reload else None,
        log_level='info',
        # open SSE streams never finish by themselves; without this a restart would hang on them
        timeout_graceful_shutdown=3,
    )


if __name__ == '__main__':
    main()
