import logging
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from api.aionode.env import ThorEnvironment, MAINNET, MULTICHAIN_STAGENET_ENVIRONMENT
from lib.constants import NetworkIdents
from lib.date_utils import parse_timespan_to_seconds
from lib.path import get_app_path
from lib.utils import strip_trailing_slash


class SubConfig:
    def __init__(self, config_data, parent_path=''):
        self._root_config = config_data
        self.parent_path = parent_path

    def get(self, path: str = None, default=None, pure=False) -> 'SubConfig':
        if path is None or path == '':
            return self._root_config

        if isinstance(path, int):
            # single number => subscript of list
            components = [path]
        else:
            components = map(str.strip, path.split('.'))

        sub_config = self._root_config
        try:
            for component in components:
                if isinstance(sub_config, (list, tuple)):
                    sub_config = sub_config[int(component)]
                elif isinstance(sub_config, dict):
                    sub_config = sub_config[component]
                else:
                    raise LookupError(f'Cannot handle config path "{self.parent_path}.{path}"!')

            if isinstance(sub_config, (list, tuple, dict)):
                return (
                    sub_config if pure else SubConfig(sub_config, parent_path=f'{self.parent_path}.{path}')
                ) if (default is None or isinstance(default, SubConfig)) else sub_config
            else:
                # primitive => always pure!
                return sub_config
        except LookupError:
            full_path = f'{self.parent_path}.{path}' if self.parent_path else path
            if default is not None:
                logging.warning(f'Config path "{full_path}" not found! Using default value: {default}')
                return default
            else:
                raise LookupError(f'Config path "{full_path}" not found!')

    def get_pure(self, path=None, default=None) -> Any:
        return self.get(path, default, pure=True)

    def as_int(self, path: str = None, default=None):
        return int(self.get(path, default))

    def as_float(self, path: str = None, default=None):
        return float(self.get(path, default))

    def as_str(self, path: str = None, default=None):
        return str(self.get(path, default))

    def as_list(self, path: str = None, default=None):
        data = self.get(path, default)
        return list(data.contents if isinstance(data, SubConfig) else data)

    @property
    def contents(self):
        return self._root_config

    def as_interval(self, path: str = None, default=None):
        return parse_timespan_to_seconds(self.as_str(path, default))

    @property
    def as_seconds(self):
        return parse_timespan_to_seconds(self._root_config)

    def __int__(self):
        return int(self._root_config)

    def __float__(self):
        return float(self._root_config)

    def __str__(self):
        return str(self._root_config)

    def __getattr__(self, item) -> 'SubConfig':
        return self.get(item)

    def __getitem__(self, item) -> 'SubConfig':
        return self.get(item)


class Config(SubConfig):
    DEFAULT_ENV_FILE = '.env'

    DEFAULT_CONFIG_FILES = [
        '/config/config.yaml',
        '../config.yaml',
        'config.yaml',
    ]

    def _load_env(self):
        env_file = self.DEFAULT_ENV_FILE
        if not os.path.exists(env_file):
            # try to locate it in the parent directory
            env_file = f'../{env_file}'
            if not os.path.exists(env_file):
                logging.error(f'Cannot find env file "{env_file}"!')
                exit(-404)

        load_dotenv(env_file)

    def __init__(self, name=None, data=None):
        logging.info(f'App path is "{get_app_path()}"')

        self._load_env()

        if data is None:
            if name:
                self._config_name = name
            else:
                if len(sys.argv) >= 2 and 'pytest' not in sys.argv[0]:
                    self._config_name = sys.argv[1]
                else:
                    # self._config_name = self.DEFAULT
                    for config_file in self.DEFAULT_CONFIG_FILES:
                        if Path(config_file).exists():
                            self._config_name = config_file
                            break

            logging.info(f'Loading config from "{self._config_name}".')
            with open(self._config_name, 'r') as f:
                data = yaml.load(f, Loader=yaml.SafeLoader)

        super().__init__(data)

        self.network_id = self.get('thor.network_id', NetworkIdents.MAINNET)

    @property
    def get_timeout_global(self):
        return self.as_interval('thor.timeout', 10.0)

    def get_thor_env_by_network_id(self, backup=False) -> ThorEnvironment:
        network_id = self.network_id

        if network_id == NetworkIdents.TESTNET_MULTICHAIN:
            raise Exception('No more Testnet! Please use the Stagenet')
        elif network_id in (NetworkIdents.CHAOSNET_MULTICHAIN, NetworkIdents.MAINNET):
            ref_env = MAINNET.copy()
            ref_env = self._load_custom_urls(ref_env, backup)
        elif network_id == NetworkIdents.STAGENET_MULTICHAIN:
            ref_env = MULTICHAIN_STAGENET_ENVIRONMENT.copy()
        else:
            raise KeyError('unsupported network ID!')

        ref_env.timeout = self.get_timeout_global

        return ref_env

    def _load_custom_urls(self, ref_env, backup):
        node_key = 'thor.node.backup_node_url' if backup else 'thor.node.node_url'
        node_url = self.as_str(node_key, '')
        if node_url:
            ref_env.thornode_url = strip_trailing_slash(node_url)

        rpc_url = self.as_str('thor.node.rpc_node_url', '')
        if rpc_url:
            ref_env.rpc_url = strip_trailing_slash(rpc_url)

        midgard_url = self.as_str('thor.midgard.public_url', '')
        if midgard_url:
            ref_env.midgard_url = strip_trailing_slash(midgard_url)
        return ref_env

    @property
    def admins(self):
        return [int(a) for a in self.get('telegram.admins', [])]

    @property
    def first_admin_id(self):
        return self.admins[0]

    def is_admin(self, user_id):
        return user_id in self.admins

    @property
    def sleep_step(self):
        return self.as_interval('startup_step_delay', 3)

    @property
    def is_debug_mode(self):
        return bool(self.get_pure('debug_mode', False))
