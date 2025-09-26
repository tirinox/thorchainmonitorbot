import asyncio
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
        self.dbg_log_full_requests = False

    async def render(self, template_name: str, parameters: dict):
        for attempt in range(self._count):
            try:
                return await self._render(template_name, parameters)
            except Exception as e:
                if attempt == self._count - 1:
                    raise
                self.logger.error(f'#{attempt}: Failed to render {template_name = }. {e = }')
                await asyncio.sleep(self._step_timeout)

    async def _render(self, template_name: str, parameters: dict):
        correlation_id = str(random_hex())

        message = {
            'template_name': template_name,
            'parameters': parameters,
            'correlation_id': correlation_id,
        }

        if self.dbg_log_full_requests:
            json_data = json.dumps(message, indent=2)
            self.logger.info(f"Request:\n\n{json_data}\n\n")

        async with self.deps.session.post(self.url, json=message) as response:
            self.logger.info(f'Rendering {template_name = }')
            if response.status != 200:
                try:
                    text = await response.text()
                except Exception as e:
                    self.logger.error(f'Failed to get error text: {e}')
                    text = '<no text>'
                raise ValueError(f'Failed to render. Code: {response.status}. Result: {text!r}')

            return await response.read()
