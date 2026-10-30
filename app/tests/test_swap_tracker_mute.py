import pytest

from comm.localization.eng_base import BaseLocalization
from models.swap_track import SwapTrack
from notify.personal.swap_tracker import PersonalSwapTracker

ME, OTHER = '111', '222'
MY_ADDR = 'bc1p' + 'x' * 58  # a taproot address: longer than the callback data allows


class FakeWatchlist:
    def __init__(self, nodes):
        self.nodes = nodes  # user -> set of addresses

    async def all_nodes_for_user(self, user):
        return list(self.nodes.get(str(user), ()))

    async def set_user_to_node(self, user, node, value):
        (self.nodes.setdefault(user, set()).add if value else self.nodes.setdefault(user, set()).discard)(node)


def make_track(tx_id, users, from_address=MY_ADDR, dest_address='0xdest'):
    return SwapTrack(tx_id=tx_id, users=users, from_address=from_address, dest_address=dest_address,
                     in_asset='BTC.BTC', in_amount=10 ** 8, out_asset='ETH.ETH', volume_usd=1.0, memo_str='',
                     start_height=1, started_ts=0.0)


def make_tracker(tracks, nodes):
    tracker = PersonalSwapTracker.__new__(PersonalSwapTracker)
    tracker.watchlist = FakeWatchlist(nodes)
    saved, dropped = {}, []

    async def load_active():
        return tracks

    async def save(track, activate=False):
        saved[track.tx_id] = dict(track.users)

    async def drop(track):
        dropped.append(track.tx_id)

    tracker.load_active, tracker._save, tracker._drop = load_active, save, drop
    return tracker, saved, dropped


def test_mute_query_fits_telegram():
    q = PersonalSwapTracker.mute_query(MY_ADDR)
    assert len(q.encode()) <= 64
    assert MY_ADDR.startswith(q.split(':', 1)[1])


@pytest.mark.asyncio
async def test_mute_keyboard_only_for_own_wallet():
    loc = BaseLocalization.__new__(BaseLocalization)
    tracker, _, _ = make_tracker([], {ME: {MY_ADDR}})
    track = make_track('A', {ME: SwapTrack.ROLE_SENDER, OTHER: SwapTrack.ROLE_WATCHER})

    kb = await tracker._mute_keyboard(loc, track, ME)
    assert kb.inline_keyboard[0][0].callback_data == PersonalSwapTracker.mute_query(MY_ADDR)
    assert await tracker._mute_keyboard(loc, track, OTHER) is None  # /track watcher: no wallet of theirs


@pytest.mark.asyncio
async def test_mute_address_quiets_active_swaps():
    tracks = [
        make_track('A', {ME: SwapTrack.ROLE_SENDER, OTHER: SwapTrack.ROLE_SENDER}),
        make_track('B', {ME: SwapTrack.ROLE_SENDER}),
        make_track('C', {ME: SwapTrack.ROLE_WATCHER}),  # asked by /track: stays
        make_track('D', {ME: SwapTrack.ROLE_SENDER}, from_address='bc1qanother'),  # another wallet: stays
    ]
    tracker, saved, dropped = make_tracker(tracks, {ME: {MY_ADDR, 'bc1qanother'}})

    await tracker.mute_address(int(ME), MY_ADDR)

    assert tracker.watchlist.nodes[ME] == {'bc1qanother'}
    assert saved == {'A': {OTHER: SwapTrack.ROLE_SENDER}}
    assert dropped == ['B']
