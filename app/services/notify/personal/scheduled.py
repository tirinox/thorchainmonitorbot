import asyncio

from services.dialog.picture.lp_picture import generate_yield_picture
from services.jobs.fetch.runeyield import get_rune_yield_connector
from services.lib.date_utils import today_str, MONTH
from services.lib.delegates import INotified
from services.lib.depcont import DepContainer
from services.lib.draw_utils import img_to_bio
from services.lib.scheduler import Scheduler
from services.lib.settings_manager import SettingsManager
from services.lib.utils import WithLogger
from services.notify.channel import BoardMessage, ChannelDescriptor


class PersonalPeriodicNotificationService(WithLogger, INotified):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

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

    async def unsubscribe(self, user_id, address, pool):
        key = self.key(user_id, address, pool)
        await self.deps.scheduler.cancel(key)

    async def toggle_subscription(self, user_id, address, pool, period):
        if await self.when_next(user_id, address, pool) is not None:
            await self.unsubscribe(user_id, address, pool)
        else:
            await self.subscribe(user_id, address, pool, period)

    async def on_data(self, sender: Scheduler, ident: str):
        user_id, address, pool = self.key_parts(ident)
        asyncio.create_task(self._deliver_report(user_id, address, pool))

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
        caption = loc.notification_text_regular_lp_report(user, address, pool, lp_report)

        # Send it to the user
        settings = await self.deps.settings_manager.get_settings(user)
        platform = SettingsManager.get_platform(settings)
        await self.deps.broadcaster.safe_send_message_rate(
            ChannelDescriptor(platform, user),
            BoardMessage.make_photo(picture_bio, caption=caption),
            disable_web_page_preview=True
        )
        self.logger.info(f'Report for {user}/{address}/{pool} sent successfully.')
