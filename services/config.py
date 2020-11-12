import sys

import yaml
from dotenv import load_dotenv
from prodict import Prodict

load_dotenv()


class Config(Prodict):
    DEFAULT = 'config.yaml'

    def __init__(self):
        self._config_name = sys.argv[1] if len(sys.argv) >= 2 else self.DEFAULT
        with open(self._config_name, 'r') as f:
            data = yaml.load(f, Loader=yaml.SafeLoader)
        super().__init__(**data)
