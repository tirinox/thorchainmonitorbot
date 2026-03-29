from collections import defaultdict

from jobs.scanner.block_result import BlockResult
from lib.delegates import INotified
from lib.depcont import DepContainer
from lib.logs import WithLogger
from models.events import EventSwap, parse_swap_and_out_event


class RapidSwapRecorder(INotified, WithLogger):
	"""
	Minimal rapid-swap recorder scaffold.

	Current scope:
	  - receives a scanned `BlockResult`
	  - inspects `end_block_events`
	  - groups `swap` events by inbound tx id
	  - identifies tx ids that have more than one swap event in the same block

	Persistence and downstream reporting will be added later.
	"""

	def __init__(self, deps: DepContainer):
		super().__init__()
		self.deps = deps
		self.last_seen_block_no = 0
		self.last_rapid_candidates: dict[str, list[EventSwap]] = {}

	@staticmethod
	def iter_swap_events(block: BlockResult):
		for raw_event in block.end_block_events:
			parsed_event = parse_swap_and_out_event(raw_event)
			if isinstance(parsed_event, EventSwap):
				yield parsed_event

	def collect_rapid_swap_candidates(self, block: BlockResult) -> dict[str, list[EventSwap]]:
		grouped_by_tx_id: dict[str, list[EventSwap]] = defaultdict(list)

		for swap_event in self.iter_swap_events(block):
			if swap_event.tx_id:
				grouped_by_tx_id[swap_event.tx_id].append(swap_event)

		return {
			tx_id: swap_events
			for tx_id, swap_events in grouped_by_tx_id.items()
			if len(swap_events) > 1
		}

	async def on_data(self, sender, data: BlockResult):
		self.last_seen_block_no = int(data.block_no or 0)
		self.last_rapid_candidates = self.collect_rapid_swap_candidates(data)

		if self.last_rapid_candidates:
			self.logger.info(
				f'RapidSwapRecorder found {len(self.last_rapid_candidates)} '
				f'rapid-swap candidate txs in block #{data.block_no}'
			)

