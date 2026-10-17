"""
Personal swap tracker: follows a swap of a watched wallet from the inbound to the outbound (or the refund)
and tells the user what happens, and why it is late when it is.

The swap starts come from SwapStartDetectorFromBlock. Then every tracked tx is polled through
/thorchain/tx/status (and /thorchain/swap/streaming for a streaming swap); a message goes out only when the stage
changes, when a streaming swap has run for a while, or when a delay has a (new) explanation.
The final picture comes from the events the block scanner stores for the swap (EventDatabase).
"""
import inspect
import re
from contextlib import suppress
from typing import Optional, Dict, List, Callable, Union

from api.aionode.types import ThorTxStatus
from jobs.fetch.base import BaseFetcher
from jobs.scanner.event_db import EventDatabase
from jobs.scanner.swap_start_detector import SwapStartDetectorFromBlock
from lib.config import SubConfig
from lib.date_utils import now_ts, MINUTE, HOUR, DAY
from lib.db import DB
from lib.delegates import INotified
from lib.depcont import DepContainer
from lib.settings_manager import SettingsManager, SettingsContext
from models.asset import Asset
from models.mimir import adv_swap_queue_enabled
from models.node_watchers import UserWatchlist
from models.s_swap import AlertSwapStart
from models.swap_track import SwapTrack, SwapStage, StageInfo, derive_stage, diagnose, DiagCtx, Diagnosis, \
    swap_summary
from models.tx import ThorAction, EventLargeTransaction
from notify.channel import ChannelDescriptor, BoardMessage


class SwapWatchlist(UserWatchlist):
    def __init__(self, db: DB):
        super().__init__(db, 'SwapTracker')


MessageBuilder = Callable[..., Union[str, BoardMessage, None]]  # (loc, name_map, user) -> message, may be async


class PersonalSwapTracker(BaseFetcher, INotified):
    KEY_ACTIVE = 'SwapTrack:Active'
    MSG_TYPE = 'personal:swap_track'

    PROGRESS_EVERY_SEC = 10 * MINUTE  # a long streaming swap reports its progress this often
    DIAG_REPEAT_SEC = HOUR  # the same explanation of a delay is not repeated more often
    FAILED_AFTER_SEC = 2 * MINUTE  # a finalised swap with nothing planned to pay out this long has failed

    def __init__(self, deps: DepContainer):
        cfg = deps.cfg.get('personal.swap_tracker', SubConfig({}))  # a config without the section gets the defaults
        super().__init__(deps, cfg.as_interval('poll_period', '20s'))
        self.watchlist = SwapWatchlist(deps.db)
        self._ev_db = EventDatabase(deps.db)
        self.delay_warn_after = cfg.as_interval('delay_warn_after', '10m')
        self.give_up_after = cfg.as_interval('give_up_after', '24h')
        self.max_active_per_user = cfg.as_int('max_active_per_user', 20)
        self.queue_congested = deps.cfg.as_int('queue.threshold.congested', 20)
        self.ttl = int(self.give_up_after + DAY)
        self._thor_height = 0
        self._thor_height_ts = 0.0

    # ------------------------------------ storage ------------------------------------

    @staticmethod
    def key(tx_id):
        return f'SwapTrack:{tx_id}'

    async def _save(self, track: SwapTrack, activate=False):
        r = await self.deps.db.get_redis()
        await r.set(self.key(track.tx_id), track.to_json(), ex=self.ttl)
        if activate:
            await r.sadd(self.KEY_ACTIVE, track.tx_id)

    async def _drop(self, track: SwapTrack):
        # the record stays until its TTL, so a late repeat of the swap start does not start it again
        r = await self.deps.db.get_redis()
        await r.srem(self.KEY_ACTIVE, track.tx_id)

    async def load_active(self) -> List[SwapTrack]:
        r = await self.deps.db.get_redis()
        tx_ids = await r.smembers(self.KEY_ACTIVE)
        if not tx_ids:
            return []
        raw = await r.mget([self.key(tx_id) for tx_id in tx_ids])
        tracks = []
        for tx_id, s in zip(tx_ids, raw):
            if s:
                tracks.append(SwapTrack.from_json(s))
            else:
                await r.srem(self.KEY_ACTIVE, tx_id)  # expired
        return tracks

    # ------------------------------------ swap start ------------------------------------

    async def on_data(self, sender, swap: AlertSwapStart):
        if swap.is_limit:
            return  # a limit order may wait for days; not for this tracker
        try:
            await self._start_tracking(swap)
        except Exception as e:
            self.logger.exception(f'Failed to start tracking {swap.tx_id}: {e!r}')

    THORNAME_RE = re.compile(r'[a-z0-9\-_+]{1,30}')  # what an address never looks like

    async def _resolve_thorname(self, address: str, chain: str) -> str:
        """
        The memo may name the destination by a THORName; the chain resolves it to the alias of the output's chain
        (the outbound goes there), so the tracker must too, or the recipient is never matched
        """
        if not address or not self.THORNAME_RE.fullmatch(address):
            return address
        try:
            thor_name = await self.deps.name_service.lookup_thorname_by_name(address, forced=True)
            if thor_name:
                alias = next((a.address for a in thor_name.aliases if a.chain == chain), '')
                return alias or address
        except Exception as e:
            self.logger.warning(f'THORName {address!r} lookup failed: {e!r}')
        return address

    async def _users_of_swap(self, swap: AlertSwapStart) -> Dict[str, str]:
        memo = swap.memo
        out_chain = Asset(swap.out_asset).chain
        from_addr = swap.from_address
        dest = await self._resolve_thorname(memo.dest_address, out_chain)
        refund = await self._resolve_thorname(memo.refund_address, Asset(swap.in_asset).chain)
        addresses = [a for a in (from_addr, dest, refund) if a]
        addr_to_users = await self.watchlist.all_users_for_many_nodes(addresses)

        users = {}
        for user in addr_to_users.get(dest) or ():
            users[str(user)] = SwapTrack.ROLE_RECIPIENT
        for addr in (refund, from_addr):
            for user in addr_to_users.get(addr) or ():
                users[str(user)] = SwapTrack.ROLE_SENDER
        return users

    RESULT_STARTED = 'started'
    RESULT_FINISHED = 'finished'  # the swap was over already: the summary went out at once
    RESULT_ALREADY = 'already'
    RESULT_NOT_FOUND = 'not_found'
    RESULT_NOT_SWAP = 'not_swap'

    @staticmethod
    def normalize_tx_id(s: str) -> str:
        """A THORChain tx id out of what the user typed: '' when it is not one"""
        s = (s or '').strip().removeprefix('0x').removeprefix('0X').upper()
        return s if re.fullmatch(r'[0-9A-F]{64}', s) else ''

    async def track_by_hash(self, tx_id: str, user_id, loc=None):
        """
        The /track command: follow a swap for this user whether or not a wallet of theirs is in it.
        Returns (result, text): with a loc, the text of the reply for a started track (the message of the start,
        with the progress), None otherwise.
        """
        status = await self.deps.thor_connector.query_tx_status(tx_id)
        if not status or not status.tx:
            return self.RESULT_NOT_FOUND, None

        # /tx/status gives the inbound as a common.Tx: the shape the block detector reads a swap start from
        detector = SwapStartDetectorFromBlock(self.deps, dedup_component='swap_tracker_manual')
        detector.ph = await self.deps.pool_cache.get()
        height = await self.deps.last_block_cache.get_thor_block()
        swap = await detector.make_swap_start_event(status.tx, tx_id, height,
                                                    is_deposit=status.tx.get('chain') == 'THOR')
        if not swap or swap.is_limit:
            return self.RESULT_NOT_SWAP, None

        return await self._start_tracking(swap, users={str(user_id): SwapTrack.ROLE_WATCHER}, status=status,
                                          reply_loc=loc)

    async def _start_tracking(self, swap: AlertSwapStart, users: Dict[str, str] = None,
                              status: ThorTxStatus = None, reply_loc=None):
        """Returns (result, text): the text is the message of the start when reply_loc asks for it instead of a send"""
        manual = users is not None  # asked by /track, not found by the scanner
        r = await self.deps.db.get_redis()
        exists = await r.exists(self.key(swap.tx_id))

        if not manual:
            # found by the block scanner: the swap of a watched wallet
            users = await self._users_of_swap(swap)
            if not users or exists:
                return self.RESULT_ALREADY, None

            # an address of a bot swaps all day long: cap the swaps followed for one user
            active = await self.load_active()
            for user in list(users):
                if sum(user in t.users for t in active) >= self.max_active_per_user:
                    self.logger.warning(f'User {user} has too many tracked swaps, skipping {swap.tx_id}')
                    users.pop(user)
            if not users:
                return self.RESULT_ALREADY, None
        elif exists and await r.sismember(self.KEY_ACTIVE, swap.tx_id):
            # asked by /track while the swap is already followed: just add the user to it
            track = SwapTrack.from_json(await r.get(self.key(swap.tx_id)))
            track.users.update(users)
            await self._save(track)
            return self.RESULT_ALREADY, None

        now = now_ts()
        dest_address = await self._resolve_thorname(swap.memo.dest_address, Asset(swap.out_asset).chain) \
            or swap.destination_address
        track = SwapTrack(
            tx_id=swap.tx_id,
            users=users,
            from_address=swap.from_address,
            dest_address=dest_address,
            in_asset=swap.in_asset,
            in_amount=swap.in_amount,
            out_asset=swap.out_asset,
            volume_usd=swap.volume_usd,
            memo_str=swap.memo_str,
            start_height=swap.block_height,
            started_ts=now,
            is_streaming=swap.is_streaming,
            quantity=swap.quantity or 1,
            interval=swap.interval or 0,
            stage=SwapStage.OBSERVED,
            stage_since_ts=now,
        )
        await self._load_quote(track, swap)

        info = StageInfo(SwapStage.OBSERVED)
        with suppress(Exception):
            status = status or await self.deps.thor_connector.query_tx_status(track.tx_id)
            if status:
                streaming = None
                if track.is_streaming and status.get_stage('swap_status').get('pending'):
                    # the memo may leave the quantity to the network: the queue knows the real one
                    streaming = await self.deps.thor_connector.query_streaming_swap(track.tx_id)
                    if streaming and streaming.quantity:
                        track.quantity, track.interval = streaming.quantity, streaming.interval
                info = derive_stage(status, streaming)
        track.stage = info.stage

        self.logger.info(f'Tracking swap {track.tx_id} for {len(users)} users, stage {info.stage}')
        await self._save(track, activate=True)

        if info.is_terminal:
            # over already (a native swap is done within a block): the summary alone, no "detected";
            # when the scanner has not stored the outbound yet, the summary follows on the next poll
            track.known_start = not manual  # /track of an old swap: no idea when it started
            finished = await self._finish(track, info)
            return (self.RESULT_FINISHED if finished else self.RESULT_STARTED), None

        text = None
        if reply_loc is not None:
            # /track: the start goes as the reply to the command, not as a separate message
            user = next(iter(users))
            name_map = await self._name_map_for(track, user)
            text = reply_loc.notification_text_swap_track_started(track, info, name_map, user, manual=True)
        else:
            await self._send_all(track, lambda loc, nm, user: loc.notification_text_swap_track_started(
                track, info, nm, user))
        track.next_poll_ts = now + self.sleep_period
        await self._save(track)
        return self.RESULT_STARTED, text

    async def _load_quote(self, track: SwapTrack, swap: AlertSwapStart):
        try:
            quote = await self.deps.thor_connector.query_swap_quote(
                from_asset=str(Asset(swap.in_asset)),
                to_asset=str(Asset(swap.out_asset)),
                amount=swap.in_amount,
                destination=swap.memo.dest_address,
                streaming_quantity=swap.quantity,
                streaming_interval=swap.interval,
                tolerance_bps=10000,
                affiliate='t' if swap.memo.affiliates else '',
                affiliate_bps=swap.memo.affiliate_fee_bp,
                height=swap.block_height,
            )
            if quote and not quote.get('message'):
                track.expected_out = int(quote.get('expected_amount_out', 0) or 0)
                track.expected_sec = float(quote.get('total_swap_seconds', 0) or 0)
        except Exception as e:
            self.logger.warning(f'No quote for {track.tx_id}: {e!r}')

    # ------------------------------------ polling ------------------------------------

    async def fetch(self):
        tracks = await self.load_active()
        if not tracks:
            return 0

        await self._update_thor_height()

        now = now_ts()
        for track in tracks:
            if track.next_poll_ts > now:
                continue
            try:
                await self._poll(track)
            except Exception as e:
                self.logger.exception(f'Failed to poll swap {track.tx_id}: {e!r}')
                track.next_poll_ts = now_ts() + 3 * self.sleep_period
                await self._save(track)
        return len(tracks)

    async def _update_thor_height(self):
        with suppress(Exception):
            height = await self.deps.last_block_cache.get_thor_block()
            if height and height != self._thor_height:
                self._thor_height, self._thor_height_ts = height, now_ts()

    def _poll_interval(self, in_stage_sec: float) -> float:
        if in_stage_sec < 5 * MINUTE:
            return self.sleep_period
        if in_stage_sec < HOUR:
            return MINUTE
        return 5 * MINUTE

    def _diag_ctx(self, track: SwapTrack) -> DiagCtx:
        return DiagCtx(
            src_chain=track.src_chain,
            dst_chain=track.dst_chain,
            mimir=self.deps.mimir_const_holder,
            chain_info=self.deps.chain_info,
            queue=self.deps.queue_holder,
            thor_height=self._thor_height,
            thor_block_age_sec=now_ts() - self._thor_height_ts if self._thor_height else 0.0,
            queue_congested=self.queue_congested,
        )

    async def _poll(self, track: SwapTrack):
        now = now_ts()
        track.polls += 1

        status: ThorTxStatus = await self.deps.thor_connector.query_tx_status(track.tx_id)
        if not status:
            raise LookupError(f'No status for {track.tx_id}')

        streaming = None
        if track.is_streaming and status.get_stage('swap_status').get('pending'):
            with suppress(Exception):
                streaming = await self.deps.thor_connector.query_streaming_swap(track.tx_id)
        info = derive_stage(status, streaming)
        if info.nothing_planned and track.stage == SwapStage.SWAPPING and now - track.stage_since_ts > self.FAILED_AFTER_SEC:
            info.stage = SwapStage.FAILED
        if not info.is_terminal and track.expected_sec:
            # the quote's total time covers all the stages; a rapid streaming swap (interval 0) has no other estimate
            info.expected_sec = max(info.expected_sec, track.expected_sec - (now - track.started_ts))

        if info.is_terminal:
            # over: the summary goes out now, or on a later poll when the scanner has not stored the outbound yet
            if info.stage != track.stage:
                self.logger.info(f'Swap {track.tx_id}: {track.stage} -> {info.stage}')
                track.stage, track.stage_since_ts = info.stage, now
            await self._finish(track, info)
            return
        elif info.stage != track.stage:
            self.logger.info(f'Swap {track.tx_id}: {track.stage} -> {info.stage}')
            track.stage, track.stage_since_ts, track.last_diag = info.stage, now, ''
            if info.stage == SwapStage.OUTBOUND_DELAY or (info.stage == SwapStage.SWAPPING and track.is_streaming):
                # signing takes seconds and a plain swap is one block: those two stages are not announced
                await self._send_all(track, lambda loc, nm, user: loc.notification_text_swap_track_stage(
                    track, info, nm, user))
        else:
            if info.stage == SwapStage.SWAPPING and info.streaming and now - track.last_msg_ts >= self.PROGRESS_EVERY_SEC:
                await self._send_all(track, lambda loc, nm, user: loc.notification_text_swap_track_stage(
                    track, info, nm, user))

            diag = diagnose(info, self._diag_ctx(track), now - track.stage_since_ts, self.delay_warn_after)
            if diag:
                if diag.code != track.last_diag or now - track.last_diag_ts >= self.DIAG_REPEAT_SEC:
                    await self._send_all(track, lambda loc, nm, user: loc.notification_text_swap_track_delayed(
                        track, info, diag, now - track.stage_since_ts, nm, user))
                    track.last_diag, track.last_diag_ts = diag.code, now
            elif track.last_diag in Diagnosis.HALT_CODES:
                resumed = Diagnosis(track.last_diag, chain=track.src_chain if 'src' in track.last_diag else track.dst_chain)
                await self._send_all(track, lambda loc, nm, user: loc.notification_text_swap_track_resumed(
                    track, resumed))
                track.last_diag = ''

        if now - track.started_ts > self.give_up_after:
            await self._send_all(track, lambda loc, nm, user: loc.notification_text_swap_track_give_up(
                track, info, nm, user))
            await self._drop(track)
            return

        track.next_poll_ts = now + self._poll_interval(now - track.stage_since_ts)
        await self._save(track)

    # ------------------------------------ the end ------------------------------------

    async def _finish(self, track: SwapTrack, info: StageInfo) -> bool:
        """The final message. False when it waits one more poll for the block scanner to catch up."""
        action = await self._build_action(track)
        if action is None and info.stage == SwapStage.DONE and track.finish_attempts < 2:
            track.finish_attempts += 1
            track.next_poll_ts = now_ts() + self.sleep_period
            await self._save(track)
            return False

        reason = ''
        if info.stage != SwapStage.DONE:
            reason = await self._refund_reason(track.tx_id)

        ph = await self.deps.pool_cache.get()
        usd_per_rune = ph.usd_per_rune if ph else 0.0
        if action and ph:
            with suppress(Exception):
                action.calc_full_rune_amount(ph)  # the liquidity fee % is counted against this volume
        summary = swap_summary(track, info, action, ph) if info.stage == SwapStage.DONE else None

        async def build(loc, name_map, user):
            text = loc.notification_text_swap_track_finished(track, info, action, reason, usd_per_rune, name_map, user,
                                                             summary)
            photo = await self._render_card(loc, action, ph, name_map) if info.stage == SwapStage.DONE else None
            if photo is not None:
                return BoardMessage.make_photo(photo, text, 'swap_finished.png', msg_type=self.MSG_TYPE)
            return text

        await self._send_all(track, build)
        await self._drop(track)
        self.logger.info(f'Swap {track.tx_id} finished: {info.stage}')
        return True

    async def _build_action(self, track: SwapTrack) -> Optional[ThorAction]:
        try:
            props = await self._ev_db.read_tx_status(track.tx_id)
            if props and props.is_completed:
                return props.build_action(int(track.started_ts),
                                          adv_swap_queue=adv_swap_queue_enabled(self.deps.mimir_const_holder))
        except Exception as e:
            self.logger.warning(f'Cannot build the action of {track.tx_id}: {e!r}')
        return None

    async def _refund_reason(self, tx_id) -> str:
        try:
            mdg = self.deps.midgard_connector
            result = await mdg.query_transactions(mdg.urlgen.url_for_tx(txid=tx_id))
            for tx in (result.txs if result else []):
                if tx.meta_refund and tx.meta_refund.reason:
                    return tx.meta_refund.reason
        except Exception as e:
            self.logger.warning(f'No refund reason for {tx_id}: {e!r}')
        return ''

    async def _render_card(self, loc, action: Optional[ThorAction], ph, name_map):
        presenter = self.deps.alert_presenter
        if action is None or presenter is None or not getattr(presenter, 'use_renderer', False):
            return None
        try:
            in_tx, out_tx = action.in_tx[0], action.recipients_output
            event = EventLargeTransaction(
                action, ph.usd_per_rune,
                usd_volume_input=ph.convert_to_usd(in_tx.coins[0].amount_float, in_tx.first_asset),
                usd_volume_output=ph.convert_to_usd(out_tx.coins[0].amount_float, out_tx.first_asset) if out_tx else 0.0,
            )
            photo, _ = await presenter.render_swap_finish(loc, event, name_map)
            return photo
        except Exception as e:
            self.logger.warning(f'Cannot render the card of {action.tx_hash}: {e!r}')
            return None

    # ------------------------------------ delivery ------------------------------------

    async def _name_map_for(self, track: SwapTrack, user, name_map=None):
        """THORNames of the swap's addresses joined with the user's own wallet names"""
        if name_map is None:
            name_map = await self.deps.name_service.safely_load_thornames_from_address_set(
                [a for a in (track.from_address, track.dest_address) if a])
        local_names = await self.deps.name_service.get_local_service(user).get_name_map()
        return name_map.joined_with(local_names) if local_names else name_map

    async def _send_all(self, track: SwapTrack, build: MessageBuilder):
        settings_dic = await self.deps.settings_manager.get_settings_multi(list(track.users.keys()))
        name_map = await self.deps.name_service.safely_load_thornames_from_address_set(
            [a for a in (track.from_address, track.dest_address) if a])

        for user in track.users:
            settings = settings_dic.get(user, {})
            if SettingsContext.is_inactive_s(settings):
                continue
            try:
                loc = await self.deps.loc_man.get_from_db(user, self.deps.db)
                user_name_map = await self._name_map_for(track, user, name_map)

                message = build(loc, user_name_map, user)
                if inspect.isawaitable(message):
                    message = await message
                if isinstance(message, str):
                    message = BoardMessage(message.strip(), msg_type=self.MSG_TYPE)
                if message is None or message.is_empty:
                    continue

                platform = SettingsManager.get_platform(settings)
                await self.deps.broadcaster.safe_send_message_rate(
                    ChannelDescriptor(platform, user), message, disable_web_page_preview=True)
            except Exception as e:
                self.logger.exception(f'Failed to notify user {user} about swap {track.tx_id}: {e!r}')

        track.last_msg_ts = now_ts()
