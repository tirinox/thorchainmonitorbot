from jobs.fetch.chain_id import EventChainId, AlertChainIdChange
from lib.confwin import ConfidenceWindow
from lib.cooldown import Cooldown
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.logs import WithLogger


class ChainIdNotifier(INotified, WithDelegates, WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        notify_cd_sec = deps.cfg.as_interval('chain_id.cooldown', '5h')
        self.cd = Cooldown(self.deps.db, 'ChainIdNotifier', notify_cd_sec)
        self._window = ConfidenceWindow(
            size=deps.cfg.get('chain_id.confidence_window_size', 20),
            threshold=0.666667
        )

    async def on_data(self, sender, event: EventChainId):
        previous = self._window.most_common(full_check=True)
        self._window.append(event.chain_id)

        # print(f'{self._window.queue} ({len(self._window)})')
        # print(f'Current: {event.chain_id!r}, previous: {previous}')

        if self._window.most_common(full_check=True) == event.chain_id:
            if previous is not None and previous != event.chain_id:
                self.logger.info(f'Network ident changed to {event.chain_id}')

                if await self.cd.can_do():
                    await self.pass_data_to_listeners(AlertChainIdChange(
                        previous, event.chain_id
                    ))
                    await self.cd.do()
