import json

from jobs.fetch.mimir import ConstMimirFetcher, MimirTuple
from lib.cooldown import Cooldown
from lib.date_utils import parse_timespan_to_seconds
from lib.delegates import INotified, WithDelegates
from lib.depcont import DepContainer
from lib.utils import WithLogger
from models.mimir import MimirVoteManager, MimirVoteOption, MimirVoting, AlertMimirVoting


class VotingNotifier(INotified, WithDelegates, WithLogger):
    IGNORE_IF_THERE_ARE_MORE_UPDATES_THAN = 6

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        cfg = deps.cfg.get('constants.voting')
        self.notification_cd_time = parse_timespan_to_seconds(cfg.as_str('notification.cooldown'))
        assert self.notification_cd_time > 0

    KEY_PREV_STATE = 'NodeMimir:Voting:PrevState'

    async def read_prev_state(self):
        prev_state = await self.deps.db.redis.get(self.KEY_PREV_STATE)
        try:
            return json.loads(prev_state)
        except (TypeError, json.decoder.JSONDecodeError):
            return {}

    async def _clear_prev_state(self):
        await self.deps.db.redis.delete(self.KEY_PREV_STATE)

    async def _save_prev_state(self, manager: MimirVoteManager):
        data = {}
        for voting in manager.all_voting_list:
            options = {}
            for option in voting.options.values():
                option: MimirVoteOption
                options[option.value] = option.progress
            data[voting.key] = options

        await self.deps.db.redis.set(self.KEY_PREV_STATE, json.dumps(data))

    async def _on_progress_changed(self, key, prev_progress, voting: MimirVoting, vote_option: MimirVoteOption):
        cd = Cooldown(self.deps.db, f'VotingNotification:{key}:{vote_option.value}', self.notification_cd_time)
        if await cd.can_do():
            await self.pass_data_to_listeners(AlertMimirVoting(
                holder=self.deps.mimir_const_holder,
                voting=voting, triggered_option=vote_option,
            ))
            await cd.do()

    async def on_data(self, sender: ConstMimirFetcher, data: MimirTuple):
        holder = self.deps.mimir_const_holder

        prev_state = await self.read_prev_state()

        events = []
        for voting in holder.voting_manager.all_voting_list:
            prev_voting = prev_state.get(voting.key)
            if not prev_voting:  # ignore for the first time to avoid spamming
                continue
            # if voting.passed:
            #     continue  # do not show progress on the voting which has already passed and adopted
            for option in voting.options.values():
                prev_progress = prev_voting.get(str(option.value))  # str(.), that's because JSON keys are strings

                if prev_progress != option.progress:
                    events.append((voting.key, prev_progress, voting, option))
                    # await self._on_progress_changed(voting.key, prev_progress, voting, option)

        # no flood after churn
        if len(events) > self.IGNORE_IF_THERE_ARE_MORE_UPDATES_THAN:
            self.logger.warning('To many voting updates; probably after churn. Ignore them for now.')
        else:
            for ev in events:
                await self._on_progress_changed(*ev)

        await self._save_prev_state(holder.voting_manager)
