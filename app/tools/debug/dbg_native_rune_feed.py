import asyncio


# tx = read_tx_from_base64(b'ClMKUQoOL3R5cGVzLk1zZ1NlbmQSPwoUcB3aXxe5wRrLLrYou5ZPUs1Lpj4SFJ7eMYD65jIupPyUaBAVIXDoM6sfGhEKBHJ1bmUSCTEyOTAwMDAwMBJXCk4KRgofL2Nvc21vcy5jcnlwdG8uc2VjcDI1NmsxLlB1YktleRIjCiECNrguIu7HQaj2Y0i9e6Ng7NatyWAs6HHNXs8YR86fe68SBAoCCAESBRCAkvQBGkDnmvI3P6S62KRctemId2fDr+YJC1UdadpK7WchcFLNIx82DYlDCy5+R+mAvi03/j9XD3LdBGdPpcF7HtlnZLsK')
# print(parse_thor_address(tx.body.messages[0].from_address))
import logging
from typing import List

from services.jobs.fetch.native_scan import NativeScanner
from services.jobs.transfer_detector import RuneTransferDetector
from services.lib.config import Config
from services.lib.delegates import INotified
from services.lib.utils import setup_logs
from services.models.transfer import RuneTransfer


class Receiver(INotified):
    async def on_data(self, sender, transfers: List[RuneTransfer]):
        for tr in transfers:
            print(tr)


async def main():
    cfg = Config()
    scanner = NativeScanner(cfg.as_str('thor.node.rpc_node_url'))

    detector = RuneTransferDetector()
    scanner.subscribe(detector)

    detector.subscribe(Receiver())

    await scanner.run()


if __name__ == '__main__':
    setup_logs(logging.INFO)
    asyncio.run(main())
