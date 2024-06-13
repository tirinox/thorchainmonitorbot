import asyncio
import random
from typing import List

from localization.eng_base import BaseLocalization
from localization.manager import LocalizationManager
from services.lib.date_utils import parse_timespan_to_seconds, now_ts, DAY
from services.lib.depcont import DepContainer
from services.lib.rate_limit import RateLimitCooldown
from services.lib.texts import shorten_text
from services.lib.utils import WithLogger
from services.notify.channel import Messengers, ChannelDescriptor, CHANNEL_INACTIVE, BoardMessage


class Broadcaster(WithLogger):
    EXTRA_RETRY_DELAY = 0.1

    def __init__(self, d: DepContainer):
        super().__init__()
        self.deps = d

        self._broadcast_lock = asyncio.Lock()
        self._rate_limit_lock = asyncio.Lock()
        self._rng = random.Random(now_ts())

        # public channels
        self.channels = list(ChannelDescriptor.from_json(j) for j in d.cfg.get_pure('broadcasting.channels'))

        startup_delay = parse_timespan_to_seconds(d.cfg.as_str('broadcasting.startup_delay', 0))
        assert DAY > startup_delay >= 0
        self._skip_all_before = now_ts() + startup_delay

        _rate_limit_cfg = d.cfg.get('personal.rate_limit')
        self._limit_number = _rate_limit_cfg.as_int('number', 10)
        self._limit_period = parse_timespan_to_seconds(_rate_limit_cfg.as_str('period', '1m'))
        self._limit_cooldown = parse_timespan_to_seconds(_rate_limit_cfg.as_str('cooldown', '5m'))

    def get_channels(self, channel_type):
        return [c for c in self.channels if c.type == channel_type]

    async def get_subscribed_channels(self):
        return await self.deps.gen_alert_settings_proc.get_general_alerts_channels(self.deps.settings_manager)

    async def notify_preconfigured_channels(self, f, *args, **kwargs):
        # todo: rename!

        subscribed_channels = await self.get_subscribed_channels()
        all_channels = self.channels + subscribed_channels

        self.logger.info(f'Total channels: {len(all_channels)}: '
                         f'predefined – ({len(self.channels)}) and subscribed – ({len(subscribed_channels)})')

        loc_man: LocalizationManager = self.deps.loc_man
        user_lang_map = {
            channels.channel_id: loc_man.get_from_lang(channels.lang)
            for channels in all_channels
        }

        if not callable(f):  # if constant
            await self.broadcast(all_channels, f, *args, **kwargs)
            return

        # not to generate same content for different channels with the same languages. test it!
        results_cached_by_lang = {}

        async def message_gen(chat_id):
            locale: BaseLocalization = user_lang_map[chat_id]

            if prev_content := results_cached_by_lang.get(locale.name):
                return prev_content

            if hasattr(locale, f.__name__):
                # if we pass function name it like "BaseLocalization.notification_text_foo"
                loc_f = getattr(locale, f.__name__)
                call_args = args
            else:
                # if it is a 3rd-party function
                loc_f = f
                call_args = [locale, *args]

            if asyncio.iscoroutinefunction(loc_f):
                result = await loc_f(*call_args, **kwargs)
            else:
                result = loc_f(*call_args, **kwargs)

            results_cached_by_lang[locale.name] = result
            return result

        await self.broadcast(all_channels, message_gen)

    async def _handle_bad_user(self, channel_info):
        self.logger.warning(f'{channel_info} is about to be paused!')
        channel_id = channel_info.channel_id
        if not channel_id:
            return

        max_fails = self.deps.cfg.get('personal.max_fails', 3)

        async with self.deps.settings_manager.get_context(channel_id) as context:
            if context.is_inactive:
                return

            # give a second change
            context.increment_fail_counter()
            if context.fail_counter >= max_fails:
                context.stop()
                self.logger.warning(f'Auto-paused alerts for {channel_id}! It is marked as "Inactive" now!')
            else:
                self.logger.warning(f'Fail counter for {channel_id} is {context.fail_counter}/{max_fails}.')

    # noinspection PyBroadException
    async def safe_send_message(self, channel_info: ChannelDescriptor,
                                message: BoardMessage, **kwargs) -> bool:
        result = False
        try:
            if isinstance(message, str):
                message = BoardMessage(message)

            if channel_info.type not in Messengers.SUPPORTED:
                self.logger.error(f'Unsupported channel type: {channel_info.type}!')
            else:
                channel_id = channel_info.channel_id
                messenger = self.deps.get_messenger(channel_info.type)
                if messenger is not None:
                    result = await messenger.send_message(channel_id, message, **kwargs)
                    if result == CHANNEL_INACTIVE:
                        await self._handle_bad_user(channel_info)
                else:
                    self.logger.error(f'{channel_info.type} bot is disabled!')
        except Exception:
            self.logger.exception('We are still safe!', stack_info=True)

        return result

    async def safe_send_message_rate(self, channel_info: ChannelDescriptor,
                                     message: BoardMessage, **kwargs) -> (bool, bool):
        async with self._rate_limit_lock:
            message = await self._form_message(message, channel_info)

            limiter = RateLimitCooldown(self.deps.db,
                                        f'SendMessage:{channel_info.short_coded}',
                                        self._limit_number,
                                        self._limit_period,
                                        self._limit_cooldown)
            outcome = await limiter.hit()
            send_result = None
            if outcome == limiter.GOOD:
                # all good: pass through
                send_result = await self.safe_send_message(channel_info, message, **kwargs)
            elif outcome == limiter.HIT_LIMIT:
                # oops! just hit the limit, tell about it once
                loc = self.deps.loc_man.get_from_lang(channel_info.lang)
                warning_message = BoardMessage(loc.RATE_LIMIT_WARNING)
                send_result = await self.safe_send_message(channel_info, warning_message, **kwargs)
            else:
                s_text = shorten_text(message.text, 200)
                self.logger.warning(f'Rate limit for channel "{channel_info.short_coded}"! Text: "{s_text}"')
            return outcome, send_result

    @staticmethod
    async def _form_message(data_source, channel_info: ChannelDescriptor, **kwargs) -> BoardMessage:
        if isinstance(data_source, BoardMessage):
            return data_source
        elif isinstance(data_source, str):
            return BoardMessage(data_source)
        elif callable(data_source):
            b_message = await data_source(channel_info.channel_id, **kwargs)
            if isinstance(b_message, BoardMessage):
                return b_message
            else:
                return BoardMessage(str(b_message))
        else:
            return BoardMessage(str(data_source))

    async def broadcast(self, channels: List[ChannelDescriptor], message, delay=0.075, **kwargs) -> int:
        if now_ts() < self._skip_all_before:
            self.logger.info('Skip message.')
            return 0

        async with self._broadcast_lock:
            count = 0

            try:
                for channel_info in channels:
                    # make from any message a BoardMessage
                    b_message = await self._form_message(message, channel_info, **kwargs)
                    if b_message.empty:
                        continue

                    send_results = await self.safe_send_message(
                        channel_info, b_message,
                        disable_web_page_preview=True,
                        disable_notification=False, **kwargs)

                    if send_results is True:
                        count += 1

                    await asyncio.sleep(delay)  # 10 messages per second (Limit: 30 messages per second)
            finally:
                self.logger.info(f"{count} messages successful sent (of {len(channels)})")

            return count
