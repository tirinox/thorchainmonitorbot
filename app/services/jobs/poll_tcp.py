import asyncio
import socket
from collections import defaultdict


class TCPPollster:
    def __init__(self, loop=None, test_timeout=0.5):
        self.test_timeout = test_timeout
        self.loop = loop or asyncio.get_event_loop()

    @staticmethod
    def test_connectivity_sync(host, port, timeout):
        s = socket.socket()
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except Exception as e:
            return False
        finally:
            s.close()

    async def test_connectivity(self, host, port):
        return await self.loop.run_in_executor(None, self.test_connectivity_sync, host, port, self.test_timeout)

    async def test_connectivity_multiple(self, ip_address_list: list, port_list: list):
        results = await asyncio.gather(
            *(self.test_connectivity(host, port) for host in ip_address_list for port in port_list)
        )
        keys = [(host, port) for host in ip_address_list for port in port_list]

        result_dict = defaultdict(dict)
        for (host, port), result in zip(keys, results):
            result_dict[host][port] = result
        return result_dict
