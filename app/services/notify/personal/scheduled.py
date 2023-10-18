import asyncio

from services.dialog.picture.lp_picture import generate_yield_picture
from services.jobs.fetch.runeyield import get_rune_yield_connector
from services.lib.date_utils import today_str, MONTH
from services.lib.db_one2one import OneToOne
from services.lib.delegates import INotified
from services.lib.depcont import DepContainer
from services.lib.draw_utils import img_to_bio
from services.lib.scheduler import Scheduler
from services.lib.settings_manager import SettingsManager
from services.lib.utils import WithLogger, generate_random_code
from services.notify.channel import BoardMessage, ChannelDescriptor


class PersonalPeriodicNotificationService(WithLogger, INotified):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self._unsub_db = OneToOne(deps.db, 'Unsubscribe')

    @staticmethod
    def key(user_id, address, pool):
        address = str(address)[:120]
        pool = str(pool)[:120]
        return f'{user_id}-{address}-{pool}'

    @staticmethod
    def key_parts(key):
        parts = key.split('-')
        return parts[0], parts[1], parts[2]

    async def cancel_all_for_user(self, user_id):
        key = self.key(user_id, '*', '*')
        await self.deps.scheduler.cancel_all_periodic(key)

    async def when_next(self, user_id, address, pool):
        key = self.key(user_id, address, pool)
        next_ts = await self.deps.scheduler.get_next_timestamp(key)
        return next_ts

    async def subscribe(self, user_id, address, pool, period):
        assert 0 < period < MONTH * 12, 'period must be less than 1 year'
        assert isinstance(pool, str) and pool, 'pool must be a non-empty string'
        assert isinstance(user_id, str) and user_id, 'user_id must be a non-empty string'
        assert isinstance(address, str) and address, 'address must be a non-empty string'

        key = self.key(user_id, address, pool)
        await self.deps.scheduler.schedule(key, period=period)

        await self._create_unsub_id(user_id, address, pool)

    async def unsubscribe(self, user_id, address, pool):
        key = self.key(user_id, address, pool)
        await self.deps.scheduler.cancel(key)

    async def unsubscribe_by_id(self, unsub_id):
        if not unsub_id:
            return False

        key = await self._unsub_db.get(unsub_id)
        if not key:
            return False

        await self.deps.scheduler.cancel(key)
        await self._unsub_db.delete(unsub_id)

        return True

    async def toggle_subscription(self, user_id, address, pool, period):
        if await self.when_next(user_id, address, pool) is not None:
            await self.unsubscribe(user_id, address, pool)
        else:
            await self.subscribe(user_id, address, pool, period)

    async def on_data(self, sender: Scheduler, ident: str):
        user_id, address, pool = self.key_parts(ident)
        asyncio.create_task(self._deliver_report_safe(user_id, address, pool))

    async def _deliver_report_safe(self, user, address, pool):
        try:
            await self._deliver_report(user, address, pool)
        except Exception as e:
            self.logger.exception(f'Error while delivering report for {user}/{address}/{pool}: {e}')
            await self.unsubscribe(user, address, pool)

    async def _deliver_report(self, user, address, pool):
        self.logger.info(f'Generating report for {user}/{address}/{pool}...')

        # Generate report
        rune_yield = get_rune_yield_connector(self.deps)
        rune_yield.add_il_protection_to_final_figures = True
        lp_report = await rune_yield.generate_yield_report_single_pool(address, pool)

        # Convert it to a picture
        value_hidden = False
        loc = await self.deps.loc_man.get_from_db(user, self.deps.db)

        picture = await generate_yield_picture(self.deps.price_holder, lp_report, loc, value_hidden=value_hidden)
        picture_bio = img_to_bio(picture, f'Thorchain_LP_{pool}_{today_str()}.png')

        local_name = await self.deps.name_service.get_local_service(user).get_wallet_local_name(address)
        unsub_id = await self._retrieve_unsub_id(user, address, pool)
        caption = loc.notification_text_regular_lp_report(user, address, pool, lp_report, local_name, unsub_id)

        # Send it to the user
        settings = await self.deps.settings_manager.get_settings(user)
        platform = SettingsManager.get_platform(settings)
        await self.deps.broadcaster.safe_send_message_rate(
            ChannelDescriptor(platform, user),
            BoardMessage.make_photo(picture_bio, caption=caption),
            disable_web_page_preview=True
        )
        self.logger.info(f'Report for {user}/{address}/{pool} sent successfully.')

    async def _create_unsub_id(self, user, address, pool):
        unique_id = generate_random_code(5)
        await self._unsub_db.put(unique_id, self.key(user, address, pool))
        self.logger.info(f'Created new unsubscribe id {unique_id} for {user}/{address}/{pool}')
        return unique_id

    async def _retrieve_unsub_id(self, user, address, pool):
        current_id = await self._unsub_db.get(self.key(user, address, pool))
        if not current_id:
            current_id = await self._create_unsub_id(user, address, pool)
        return current_id
