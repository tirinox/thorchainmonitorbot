import asyncio
import json
import operator
import os

import aiofiles

from jobs.node_churn import NodeChurnDetector
from models.node_info import NodeInfo
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
                await self.save_db_sometimes(prefix=prefix)
                return nodes

    async def save_db(self, prefix=''):
        print(f'{prefix}Saving DB: {len(self.db)} entries')
        if self.db:
            async with aiofiles.open(self.filename, 'w') as f:
                data = json.dumps(self.db)
                await f.write(data)

            print(f'{prefix}Saved file size is {get_size(self.filename)} MB')
        else:
            print(f'{prefix}Error! No data to save')

    async def save_db_sometimes(self, prefix=''):
        self.tick += 1
        if self.tick % 10 == 0:
            await self.save_db(prefix)

    async def load_db(self):
        try:
            async with aiofiles.open(self.filename, 'r') as f:
                print(f'Loading Db. Filesize is {get_size(self.filename)} MB')
                data = await f.read()
                self.db = json.loads(data)
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

    async def naive_diff(self, block1, block2):
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

    async def diff_node_set_changes(self, block1, block2):
        n1 = await self.get_nodes(block1)
        n2 = await self.get_nodes(block2)

        n1 = [NodeInfo.from_json(j) for j in n1]
        n2 = [NodeInfo.from_json(j) for j in n2]

        return NodeChurnDetector(self.app.deps).extract_changes(n2, n1)

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

