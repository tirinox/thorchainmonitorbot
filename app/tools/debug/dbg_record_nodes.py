import asyncio
import json
import logging
import operator
import os

from services.jobs.node_churn import NodeChurnDetector
from services.lib.texts import sep
from services.models.node_info import NodeInfo
from services.notify.personal.bond_provider import PersonalBondProviderNotifier
from tools.lib.lp_common import LpAppFramework


class NodesDBRecorder:
    def __init__(self, app: LpAppFramework, filename):
        self.app = app
        self.filename = filename
        self.db = {}
        self.last_block = 0
        self.ignore_keys = {
            'current_award',
            'active_block_height',
            'observe_chains',
            'signer_membership',
            'slash_points',
        }
        self.tick = 0

    @property
    def thor(self):
        return self.app.deps.thor_connector

    async def query_nodes_from_server(self, block_no):
        try:
            data = await self.thor.query_raw(f'/thorchain/nodes?height={int(block_no)}')

            # do some cleaning
            for node in data:
                node: dict
                for key in self.ignore_keys:
                    node.pop(key)

            data.sort(key=operator.itemgetter('node_address'))

            return data
        except Exception:
            pass

    async def get_nodes(self, block_no, prefix=''):
        block_no = str(block_no)
        if block_no in self.db:
            return self.db[block_no]
        else:
            nodes = None
            for _ in range(5):
                nodes = await self.query_nodes_from_server(block_no)
                if nodes:
                    break
                else:
                    await asyncio.sleep(3.0)

            if nodes:
                self.db[block_no] = nodes
                self.save_db_sometimes(prefix=prefix)
                return nodes

    def save_db(self, prefix=''):
        print(f'{prefix}Saving DB: {len(self.db)} entries')
        if self.db:
            with open(self.filename, 'w') as f:
                json.dump(self.db, f)

            print(f'{prefix}Saved file size is {get_size(self.filename)} MB')
        else:
            print(f'{prefix}Error! No data to save')

    def save_db_sometimes(self, prefix=''):
        self.tick += 1
        if self.tick % 10 == 0:
            self.save_db(prefix)

    def load_db(self):
        try:
            with open(self.filename, 'r') as f:
                print(f'Loading Db. Filesize is {get_size(self.filename)} MB')
                self.db = json.load(f)
                if not isinstance(self.db, dict):
                    self.db = {}
                print(f'Block 2 nodes DB loaded: {len(self.db)} items')
        except Exception:
            print(f'Error! DB is not loaded!')
            return {}

    async def ensure_last_block(self):
        last_blocks = await self.thor.query_last_blocks()
        last_block = last_blocks[0].thorchain
        if not last_block:
            print(f'Error! No last block! Aborting')
            return False
        else:
            print(f'{last_block = }')
            self.last_block = last_block
            return last_block

    @staticmethod
    def are_nodes_identical(nodes1, nodes2):
        return json.dumps(nodes1) == json.dumps(nodes2)

    async def batch_load(self, *blocks):
        for b in blocks:
            await self.get_nodes(b)

    async def scan(self, left_block, right_block, depth=0):
        prefix = ' ' * (depth * 2)

        if left_block >= right_block:
            print(f'{prefix}Stop branch at #{left_block}.')
            return

        print(f'{prefix}Scan start {left_block} and {right_block}; '
              f'they are {right_block - left_block} block apart.')

        left_nodes = await self.get_nodes(left_block, prefix)
        right_nodes = await self.get_nodes(right_block, prefix)

        if not left_nodes or not right_nodes:
            print(f"{prefix}ERROR Scanning this interval! Skip this!")
            return

        if not self.are_nodes_identical(left_nodes, right_nodes):
            print(f'{prefix}There is difference between blocks {left_block}...{right_block}; '
                  f'they are {right_block - left_block} block apart.')
            middle = (left_block + right_block) // 2
            await self.scan(left_block, middle, depth=depth + 1)
            await self.scan(middle + 1, right_block, depth=depth + 1)
        else:
            print(f'{prefix}There are no changes in range {left_block}..{right_block} '
                  f'({right_block - left_block} blocks)')

    async def diff(self, block1, block2):
        if block1 == block2:
            print('Same block')
            return

        async def save(block):
            nodes = await self.get_nodes(block)
            fn = f'../temp/block_{block}.json'
            with open(fn, 'w') as f:
                json.dump(nodes, f, indent=4)
            return fn

        fn1 = await save(block1)
        fn2 = await save(block2)

        os.system(f'diff "{fn1}" "{fn2}"')

    def print_db_map(self):
        min_block = min(int(b) for b in self.db.keys())
        max_block = max(int(b) for b in self.db.keys())
        r = ''
        for i in range(min_block, max_block + 1):
            r += ('o' if str(i) in self.db else '.')

        print(r)


class NodePlayer:
    def __init__(self, db: dict):
        self.db = db
        self._keys = list(sorted(int(b) for b in self.db.keys()))
        self.index = 0

    def __next__(self):
        if self.index >= len(self._keys):
            raise StopIteration
        key = self._keys[self.index]
        self.index += 1
        raw_nodes = self.db[str(key)]
        nodes = [NodeInfo.from_json(node) for node in raw_nodes]
        return key, nodes

    def __iter__(self):
        return self


def get_size(file_path):
    file_size = os.path.getsize(file_path)
    size = file_size / 1024 ** 2
    return round(size, 3)


DEFAULTS_FILE_NAME_FOR_DB = f'../temp/mainnet_nodes_db_1.json'


async def run_recorder(app: LpAppFramework):
    recorder = NodesDBRecorder(app, filename=DEFAULTS_FILE_NAME_FOR_DB)

    recorder.load_db()
    recorder.print_db_map()

    # await recorder.diff(12602377, 12602978)

    await recorder.ensure_last_block()

    start = 12529212 - 20
    await recorder.scan(left_block=start, right_block=12603435)
    recorder.save_db()


async def run_playback(app: LpAppFramework, delay=5.0):
    recorder = NodesDBRecorder(app, filename=DEFAULTS_FILE_NAME_FOR_DB)
    recorder.load_db()
    recorder.print_db_map()

    player = NodePlayer(recorder.db)

    churn_detector = NodeChurnDetector(app.deps)

    bond_provider_tools = PersonalBondProviderNotifier(app.deps)
    bond_provider_tools.log_events = True
    churn_detector.add_subscriber(bond_provider_tools)

    for block, nodes in player:
        sep(f'#{block}')
        # noinspection PyTypeChecker
        await churn_detector.on_data(None, nodes)
        await asyncio.sleep(delay)


async def main():
    app = LpAppFramework(log_level=logging.INFO)
    async with app(brief=True):
        app.deps.thor_env.timeout = 100
        # await demo_run_continuously(app)

        await run_playback(app, delay=0.01)


if __name__ == '__main__':
    asyncio.run(main())
