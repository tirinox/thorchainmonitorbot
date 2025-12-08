import asyncio
import os
import random

from lib.interchan import SimpleRPC
from tools.lib.lp_common import LpAppFramework


async def dbg_run_server(rpc: SimpleRPC):
    async def server_code(data):
        print(data)
        command = data.get('command')
        if command == 'calculate':
            x = data.get('x', 0)
            y = data.get('y', 0)
            result = x + y
            print(f'Server: calculate: {x = }, {y = }, {result = }')
            return result
        else:
            print(f'Server: Unknown command: {command}')
            return {'error': 'Unknown command'}

    await rpc.run_as_server(server_code)
    await asyncio.sleep(10_000)


async def dbg_run_client(rpc: SimpleRPC):
    await rpc.run_as_client()
    while True:
        x = random.randint(1, 10)
        y = random.randint(1, 10)
        print(f'Send RPC: {x = }, {y = }')
        response = await rpc({
            'command': 'calculate',
            'x': x,
            'y': y,
        })
        print(f'Response: {response}')
        await asyncio.sleep(3.0)


async def main():
    app = LpAppFramework()
    async with app:
        rpc = SimpleRPC(app.deps.db, '_dbg:SimpleRPC_test')
        mode = os.environ.get('MODE')
        if mode == 'server':
            await dbg_run_server(rpc)
        elif mode == 'client':
            await dbg_run_client(rpc)
        else:
            print('Run it with env MODE either "server" or "client"')


if __name__ == '__main__':
    asyncio.run(main())
