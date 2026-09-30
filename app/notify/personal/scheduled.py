import asyncio
import re
from typing import NamedTuple

from comm.picture.lp_picture import generate_yield_picture
from jobs.runeyield import get_rune_yield_connector
from lib.date_utils import today_str, MONTH
from lib.db_one2one import OneToOne
from lib.delegates import INotified
from lib.depcont import DepContainer
from lib.draw_utils import img_to_bio
from lib.logs import WithLogger
from lib.scheduler import PrivateScheduler
from lib.settings_manager import SettingsManager, SettingsContext
from lib.utils import generate_random_code
from notify.channel import BoardMessage, ChannelDescriptor


class PersonalIdTriplet(NamedTuple):
    user_id: str
    address: str
    pool: str

    def __str__(self):
        return f'{self.user_id}/{self.address}/{self.pool}'

    # user_id-address-pool: a Telegram group id is negative and a pool name may contain '-', an address may not
    KEY_RE = re.compile(r'(-?[^-]+)-([^-]+)-(.*)')

    @classmethod
    def from_key(cls, key):
        m = cls.KEY_RE.fullmatch(key)
        if not m:
            raise ValueError(f'Not a subscription key: {key!r}')
        return cls(*m.groups())

    @classmethod
    def wide_for_user_id(cls, user_id):
        return cls(user_id, '*', '*')

    @property
    def as_key(self):
        address = str(self.address)[:120]
        pool = str(self.pool)[:120]
        return f'{self.user_id}-{address}-{pool}'


class PersonalPeriodicNotificationService(WithLogger, INotified):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self._unsub_db = OneToOne(deps.db, 'Unsubscribe')
        # a report fails for a while when Midgard is down: unsubscribe only after this many failures in a row
        self.max_report_fails = int(deps.cfg.get('personal.scheduler.max_report_fails', 3)) \
            if getattr(deps, 'cfg', None) is not None else 3

    DB_KEY_FAILS = 'PersonalReport:Fails'

    async def cancel_all_for_user(self, user_id):
        key = PersonalIdTriplet(user_id, '*', '*').as_key
        await self.deps.scheduler.cancel_all_periodic(key)

    async def when_next(self, tr: PersonalIdTriplet):
        next_ts = await self.deps.scheduler.get_next_timestamp(tr.as_key)
        return next_ts

    async def subscribe(self, tr: PersonalIdTriplet, period):
        assert 0 < period < MONTH * 12, 'period must be less than 1 year'
        assert isinstance(tr.pool, str) and tr.pool, 'pool must be a non-empty string'
        assert isinstance(tr.user_id, str) and tr.user_id, 'user_id must be a non-empty string'
        assert isinstance(tr.address, str) and tr.address, 'address must be a non-empty string'

        await self.deps.scheduler.schedule(tr.as_key, period=period)

        await self._create_unsub_id(tr)

    async def unsubscribe(self, tr: PersonalIdTriplet):
        await self.deps.scheduler.cancel(tr.as_key)
        await self._reset_fail_counter(tr)

    async def unsubscribe_by_id(self, unsub_id, user_id) -> bool:
        """Cancels the subscription behind an /unsub_ code, but only for the chat that owns it."""
        if not unsub_id:
            return False

        key = await self._unsub_db.get(unsub_id)
        if not key:
            return False

        try:
            owner = PersonalIdTriplet.from_key(key).user_id
        except ValueError:
            owner = None  # e.g. a subscription key typed in as the code: its partner is a code, not a key
        if owner != str(user_id):
            self.logger.warning(f'Chat {user_id} tried to use unsubscribe code {unsub_id!r} of another chat')
            return False

        await self.deps.scheduler.cancel(key)
        await self._unsub_db.delete(unsub_id)

        return True

    async def toggle_subscription(self, tr: PersonalIdTriplet, period):
        if await self.when_next(tr) is not None:
            await self.unsubscribe(tr)
        else:
            await self.subscribe(tr, period)

    async def should_restore(self, ident: str):
        # users who blocked the bot don't get their lost subscriptions back, until they come back
        tr = PersonalIdTriplet.from_key(ident)
        settings = await self.deps.settings_manager.get_settings(tr.user_id)
        return not SettingsContext.is_inactive_s(settings)

    async def on_data(self, sender: PrivateScheduler, ident: str):
        tr = PersonalIdTriplet.from_key(ident)
        _ = asyncio.create_task(self._deliver_report_safe(tr))

    async def _deliver_report_safe(self, tr: PersonalIdTriplet):
        try:
            await self._deliver_report(tr)
            await self._reset_fail_counter(tr)
        except Exception as e:
            self.logger.exception(f'Error while delivering report for {tr}: {e}')

            fails = await self._count_fail(tr)
            unsubscribe = fails >= self.max_report_fails
            if unsubscribe:
                self.logger.warning(f'{fails} reports in a row failed for {tr}; unsubscribing.')
                await self.unsubscribe(tr)
            else:
                self.logger.info(f'Report {fails}/{self.max_report_fails} failed for {tr}; will try again next time.')

            try:
                await self._deliver_error_message(str(e), tr, unsubscribed=unsubscribe)
            except Exception as e:
                self.logger.exception(f'Error while delivering error message for {tr}: {e}')

    async def _count_fail(self, tr: PersonalIdTriplet) -> int:
        return int(await self.deps.db.redis.hincrby(self.DB_KEY_FAILS, tr.as_key, 1))

    async def _reset_fail_counter(self, tr: PersonalIdTriplet):
        await self.deps.db.redis.hdel(self.DB_KEY_FAILS, tr.as_key)

    async def _deliver_report(self, tr: PersonalIdTriplet):
        self.logger.info(f'Generating report for {tr}...')

        # Generate report
        rune_yield = get_rune_yield_connector(self.deps)
        lp_report = await rune_yield.generate_yield_report_single_pool(tr.address, tr.pool)

        loc, local_name, unsub_id, platform = await self._prepare_state(tr)

        # Convert it to a picture
        value_hidden = False
        ph = await self.deps.pool_cache.get()
        picture = await generate_yield_picture(ph, lp_report, loc, value_hidden=value_hidden)
        picture_bio = img_to_bio(picture, f'Thorchain_LP_{tr.pool}_{today_str()}.png')

        caption = loc.notification_text_regular_lp_report(tr.user_id, tr.address, tr.pool, lp_report, local_name,
                                                          unsub_id)

        # Send it to the user
        message = BoardMessage.make_photo(picture_bio, caption=caption, msg_type='personal:scheduled:lp_report')
        await self._deliver_message_generic(message, platform, tr.user_id)

        self.logger.info(f'Report for {tr} sent successfully.')

    async def _deliver_error_message(self, details, tr: PersonalIdTriplet, unsubscribed=True):
        loc, local_name, unsub_id, platform = await self._prepare_state(tr)
        if unsubscribed:
            text = loc.text_error_delivering_report(details, tr.address, tr.pool)
        else:
            text = loc.text_error_delivering_report_retry(details, tr.address, tr.pool)
        message = BoardMessage(text, msg_type='personal:scheduled:error')
        await self._deliver_message_generic(message, platform, tr.user_id)

    async def _deliver_message_generic(self, message: BoardMessage, platform, user):
        await self.deps.broadcaster.safe_send_message_rate(
            ChannelDescriptor(platform, user),
            message,
            disable_web_page_preview=True
        )

    async def _prepare_state(self, tr: PersonalIdTriplet):
        loc = await self.deps.loc_man.get_from_db(tr.user_id, self.deps.db)
        local_name = await self.deps.name_service.get_local_service(tr.user_id).get_wallet_local_name(tr.address)
        unsub_id = await self._retrieve_unsub_id(tr)

        # Send it to the user
        settings = await self.deps.settings_manager.get_settings(tr.user_id)
        platform = SettingsManager.get_platform(settings)
        return loc, local_name, unsub_id, platform

    async def _create_unsub_id(self, tr: PersonalIdTriplet):
        unique_id = generate_random_code(5)
        await self._unsub_db.put(unique_id, tr.as_key)
        self.logger.info(f'Created new unsubscribe id {unique_id} for {tr}')
        return unique_id

    async def _retrieve_unsub_id(self, tr: PersonalIdTriplet):
        current_id = await self._unsub_db.get(tr.as_key)
        if not current_id:
            current_id = await self._create_unsub_id(tr)
        return current_id
