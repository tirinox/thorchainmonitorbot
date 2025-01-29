import json

from lib.logs import WithLogger
from lib.utils import random_hex


class InfographicRendererRPC(WithLogger):
    def __init__(self, deps, url='http://127.0.0.1:8404/render', timeout=5.0):
        super().__init__()
        self._count = 10
        self.timeout = timeout
        self._step_timeout = 1.0
        self.deps = deps
        self.url = url

    async def render(self, template_name: str, parameters: dict):
        correlation_id = str(random_hex())

        message = {
            'template_name': template_name,
            'parameters': parameters,
            'correlation_id': correlation_id,
        }

        async with self.deps.session.post(self.url, json=message) as response:
            self.logger.info(f'Rendering {template_name = }, JSON = {json.dumps(message, indent=4)}')
            if response.status != 200:
                raise ValueError(f'Failed to render. Code: {response.status}. {message = }')

            return await response.read()
