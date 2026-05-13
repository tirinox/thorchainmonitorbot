import asyncio
import random
from contextlib import contextmanager
from contextvars import ContextVar
from typing import List, Tuple, Any

from comm.localization.eng_base import BaseLocalization
from comm.localization.manager import LocalizationManager
from lib.date_utils import parse_timespan_to_seconds, now_ts, DAY
from lib.depcont import DepContainer
from lib.logs import WithLogger
from lib.rate_limit import RateLimitCooldown
from lib.texts import shorten_text
from notify.channel import Messengers, ChannelDescriptor, CHANNEL_INACTIVE, BoardMessage


class Broadcaster(WithLogger):
    EXTRA_RETRY_DELAY = 0.1
    _ALL_CHANNELS = object()

    def __init__(self, d: DepContainer):
        super().__init__()
        self.deps = d

        self._broadcast_lock = asyncio.Lock()
        self._rate_limit_lock = asyncio.Lock()
        self._rng = random.Random(now_ts())
        self._public_channel_scope: ContextVar[Any] = ContextVar('public_broadcast_channels', default=self._ALL_CHANNELS)

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

    @staticmethod
    def _normalize_channel_selection(channels) -> list[Any] | object:
        if channels is None or channels is Broadcaster._ALL_CHANNELS:
            return Broadcaster._ALL_CHANNELS

        if isinstance(channels, str):
            raw_items = [channels]
        elif isinstance(channels, (list, tuple, set)):
            raw_items = list(channels)
        else:
            raise ValueError('Broadcast channels must be a string or a list of strings/objects.')

        normalized = []
        for item in raw_items:
            if isinstance(item, tuple) and len(item) == 2:
                channel_type = str(item[0]).strip().lower()
                channel_name = str(item[1]).strip()
                if not channel_type or not channel_name:
                    raise ValueError('Broadcast channel tuples must contain non-empty type and name values.')
                normalized.append((channel_type, channel_name))
                continue

            if isinstance(item, dict):
                channel_type = str(item.get('type', '')).strip().lower()
                channel_name = str(item.get('name', '')).strip()
                if not channel_type or not channel_name:
                    raise ValueError('Broadcast channel objects must contain non-empty "type" and "name" fields.')
                normalized.append((channel_type, channel_name))
                continue

            selector = str(item).strip()
            if selector:
                normalized.append(selector)

        return normalized

    @staticmethod
    def _channel_matches_selector(channel: ChannelDescriptor, selector: Any) -> bool:
        if isinstance(selector, tuple):
            return channel.type == selector[0] and str(channel.channel_id) == selector[1]

        selector = str(selector)
        return selector == channel.short_coded or selector == str(channel.channel_id)

    def _select_public_channels(self, requested_channels) -> list[ChannelDescriptor]:
        normalized = self._normalize_channel_selection(requested_channels)
        if normalized is self._ALL_CHANNELS:
            return list(self.channels)

        selected = []
        selected_codes = set()
        missing = []

        for selector in normalized:
            matches = [channel for channel in self.channels if self._channel_matches_selector(channel, selector)]
            if not matches:
                missing.append(selector)
                continue

            for channel in matches:
                if channel.short_coded in selected_codes:
                    continue
                selected.append(channel)
                selected_codes.add(channel.short_coded)

        if missing:
            self.logger.warning(f'Unknown broadcast channels requested: {missing!r}.')

        return selected

    @contextmanager
    def override_channels(self, channels):
        token = self._public_channel_scope.set(self._normalize_channel_selection(channels))
        try:
            yield
        finally:
            self._public_channel_scope.reset(token)

    async def get_subscribed_channels(self):
        return await self.deps.gen_alert_settings_proc.get_general_alerts_channels(self.deps.settings_manager)

    async def broadcast_to_all(self, msg_type, f, *args, channels=None, **kwargs):
        requested_channels = self._public_channel_scope.get() if channels is None else self._normalize_channel_selection(channels)
        public_channels = self._select_public_channels(requested_channels)
        subscribed_channels = [] if requested_channels is not self._ALL_CHANNELS else await self.get_subscribed_channels()
        all_channels = public_channels + subscribed_channels

        self.logger.info(f'Total channels: {len(all_channels)}: '
                         f'predefined – ({len(public_channels)}) and subscribed – ({len(subscribed_channels)}), {f}')

        loc_man: LocalizationManager = self.deps.loc_man
        user_lang_map = {
            channels.channel_id: loc_man.get_from_lang(channels.lang)
            for channels in all_channels
        }

        if not callable(f):  # if constant
            await self._broadcast_to(all_channels, f, msg_type, *args, **kwargs)
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

        await self._broadcast_to(all_channels, message_gen, msg_type)

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
    async def _safe_send_message(self, channel_info: ChannelDescriptor,
                                 message: BoardMessage, **kwargs) -> bool:
        result = False
        try:
            if not isinstance(message, BoardMessage):
                self.logger.error(f"We should not send this! {message!r} Please make it a BoardMessage!")
                return False

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
                                     message: BoardMessage, **kwargs) -> Tuple[str, bool]:
        async with self._rate_limit_lock:
            # message is already BoarMessage!
            # message = await self._form_message(message, channel_info, message.msg_type)

            limiter = RateLimitCooldown(self.deps.db,
                                        f'SendMessage:{channel_info.short_coded}',
                                        self._limit_number,
                                        self._limit_period,
                                        self._limit_cooldown)
            outcome = await limiter.hit()
            send_result = None
            if outcome == limiter.GOOD:
                # all good: pass through
                send_result = await self._safe_send_message(channel_info, message, **kwargs)
            elif outcome == limiter.HIT_LIMIT:
                # oops! just hit the limit, tell about it once
                loc = self.deps.loc_man.get_from_lang(channel_info.lang)
                warning_message = BoardMessage(loc.RATE_LIMIT_WARNING, msg_type='bot:rate_limit_warning')
                send_result = await self._safe_send_message(channel_info, warning_message, **kwargs)
            else:
                s_text = shorten_text(message.text, 200)
                self.logger.warning(f'Rate limit for channel "{channel_info.short_coded}"! Text: "{s_text}"')
            return outcome, send_result

    @staticmethod
    async def _form_message(data_source, channel_info: ChannelDescriptor, msg_type, **kwargs) -> BoardMessage:
        if isinstance(data_source, BoardMessage):
            data_source.msg_type = msg_type or data_source.msg_type
            return data_source
        elif isinstance(data_source, str):
            if not msg_type:
                raise ValueError('msg_type is required when data_source is a string')
            return BoardMessage(data_source, msg_type=msg_type)
        elif callable(data_source):
            # noinspection PyUnresolvedReferences
            b_message = await data_source(channel_info.channel_id, **kwargs)
            if isinstance(b_message, BoardMessage):
                b_message.msg_type = msg_type or b_message.msg_type
                return b_message
            else:
                if not msg_type:
                    raise ValueError(
                        'msg_type is required when data_source is a callable that does not return BoardMessage')
                return BoardMessage(str(b_message).strip(), msg_type=msg_type)
        else:
            raise ValueError(f'Unsupported message data source: {data_source!r}')

    async def _broadcast_to(self, channels: List[ChannelDescriptor], message, msg_type, delay=0.075, **kwargs) -> int:
        if now_ts() < self._skip_all_before:
            self.logger.warning('Skip message.')
            return 0

        async with self._broadcast_lock:
            count = 0

            try:
                for channel_info in channels:
                    # make from any message a BoardMessage
                    b_message = await self._form_message(message, channel_info, msg_type, **kwargs)
                    if b_message.is_empty:
                        continue

                    if not await self.deps.flagship.is_flag_set(f"{msg_type}:broadcast:{channel_info.type}"):
                        self.logger.warning(
                            f"Flag is not set for broadcasting {msg_type} to "
                            f"{channel_info.type} ({channel_info.short_coded})! Skipping.")
                        continue

                    send_results = await self._safe_send_message(
                        channel_info, b_message,
                        disable_web_page_preview=True,
                        disable_notification=False, **kwargs)

                    if send_results:
                        count += 1

                    await asyncio.sleep(delay)  # 10 messages per second (Limit: 30 messages per second)
            finally:
                self.logger.info(f"{count} messages successful sent (of {len(channels)})")

            return count
