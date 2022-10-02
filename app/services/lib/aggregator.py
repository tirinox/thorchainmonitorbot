import re
from typing import NamedTuple, Union, List

from services.lib.texts import fuzzy_search
from services.lib.utils import load_json
from services.lib.web3_helper import Web3Helper, CONTRACT_DATA_BASE_PATH


class AggregatorRecord(NamedTuple):
    address: str
    chain: str
    name: str


AggregatorSearchResult = Union[AggregatorRecord, List[AggregatorRecord], None]


# Use that source: https://gitlab.com/thorchain/thornode/-/blob/develop/x/thorchain/aggregators/dex_mainnet.go
class AggregatorResolver:
    def __init__(self, filename, data=None):
        self.filename = filename
        self._table = {}
        self.by_chain = {}
        self.by_name = {}

        if filename:
            with open(self.filename, 'r') as fp:
                data = fp.read()
        self._load(data)

    def _load(self, data):
        lines = [line.strip() for line in data.split('\n')]
        lines = filter(bool, lines)
        aggr_name = ''
        for line in lines:
            if line.startswith('//'):  # comment line contains names
                aggr_name = line[2:].strip()
            elif line.startswith('{'):  # datum line contains chain and address
                addresses = re.findall(r'`(.+?)`', line)
                chains = re.findall(r'common\.(.+?)Chain', line)
                if addresses and chains:
                    chain = chains[0]
                    aggr_address = addresses[0]
                    record = AggregatorRecord(aggr_address, chain, aggr_name)
                    if chain not in self.by_chain:
                        self.by_chain[chain] = {}
                    self.by_chain[chain][aggr_address] = record
                    self.by_name[aggr_name] = record
                    self._table[aggr_address] = record

    def search_aggregator_address(self, query: str, ambiguity=False) -> AggregatorSearchResult:
        return self._search(query, self._table.keys(), self._table, ambiguity)

    def search_by_name(self, query, ambiguity=False) -> AggregatorSearchResult:
        return self._search(query, self.by_name.keys(), self.by_name, ambiguity)

    @staticmethod
    def _search(query, keys, dic, ambiguity) -> AggregatorSearchResult:
        variants = fuzzy_search(query, keys, f=str.lower)
        if not variants:
            return None

        if len(variants) > 1:
            if ambiguity:
                raise ValueError('Aggregator search ambiguity!')
            else:
                return [dic.get(v) for v in variants]
        else:
            return dic.get(variants[0])

    def __len__(self):
        return len(self._table)

    def __getitem__(self, item):
        return self._table.get(item)


class SwapInArgs(NamedTuple):
    tc_router: str
    tc_vault: str
    tc_memo: str
    target_token: str
    amount: int
    amount_out_min: int
    deadline: int


class AggregatorContract:
    DEFAULT_ABI_AGGREGATOR = f'{CONTRACT_DATA_BASE_PATH}/aggregator.abi.json'

    def __init__(self, helper: Web3Helper):
        self.helper = Web3Helper
        self._aggregator_contract = helper.w3.eth.contract(abi=load_json(self.DEFAULT_ABI_AGGREGATOR))

    def decode_input(self, input_str):
        func, args_dic = self._aggregator_contract.decode_function_input(input_str)
        args = None
        if func.fn_name == 'swapIn':
            args = SwapInArgs(
                tc_router=args_dic.get('tcRouter'),
                tc_vault=args_dic.get('tcVault'),
                tc_memo=args_dic.get('tcMemo'),
                target_token=args_dic.get('token'),
                amount=args_dic.get('amount'),
                amount_out_min=args_dic.get('amountOutMin'),
                deadline=args_dic.get('deadline'),
            )
        return func.fn_name, args


class SwapOutArgs(NamedTuple):
    # address target, address finalAsset, address to, uint256 amountOutMin, string memo) ***
    tc_aggregator: str
    target_token: str
    to_address: str
    amount_out_min: int
    tc_memo: str


class TCRouterContract:
    DEFAULT_ABI_ROUTER = f'{CONTRACT_DATA_BASE_PATH}/tc_router_v3.abi.json'

    def __init__(self, helper: Web3Helper):
        self.helper = Web3Helper
        self._router_contract = helper.w3.eth.contract(abi=load_json(self.DEFAULT_ABI_ROUTER))

    def decode_input(self, input_str):
        func, args_dic = self._router_contract.decode_function_input(input_str)
        args = None
        if func.fn_name == 'transferOutAndCall':
            args = SwapOutArgs(
                tc_aggregator=args_dic.get('aggregator'),
                target_token=args_dic.get('finalToken'),
                to_address=args_dic.get('to'),
                amount_out_min=args_dic.get('amountOutMin'),
                tc_memo=args_dic.get('memo'),
            )
        return func.fn_name, args
