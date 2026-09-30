"""
Restore a user's "My wallets" list when it got wiped from the settings record.

The addresses live in Settings:Data:<user_id> -> personal:balance-track -> addresses. The old web settings page
replaced the whole record on save and dropped that section. The per-user watch sets survive such a save,
so the list is rebuilt from them:
  - set:UserID-2-Wallet:UserID:<user_id>        addresses with balance tracking on  -> track_balance=True
  - set:UserID-2-BondProvider:UserID:<user_id>  addresses with bond tracking on     -> the rest, track_balance=False

Usage (inside the bot container, or locally with the production .env):
    cd /app && PYTHONPATH=/app python tools/restore_wallet_list.py <user_id>            # dry run: print the plan
    cd /app && PYTHONPATH=/app python tools/restore_wallet_list.py <user_id> --apply    # write it

The previous record is printed and saved to settings_backup_<user_id>_<timestamp>.json before writing.
An existing non-empty list is never overwritten unless --force is given.
"""
import argparse
import asyncio
import json
import logging
import sys
import time

from lib.constants import Chains
from lib.settings_manager import SettingsManager
from lib.texts import sep
from notify.personal.balance import WalletWatchlist
from notify.personal.bond_provider import BondWatchlist
from notify.personal.helpers import GeneralSettings, Props
from tools.lib.lp_common import LpAppFramework

CHAIN_ORDER = {Chains.THOR: 0, Chains.BTC: 1, Chains.ETH: 2, Chains.BNB: 3, Chains.DOGE: 4}


def detect_chain(address: str) -> str:
    # same fallback as MyWalletsMenu._add_address_handler
    return Chains.detect_chain(address) or Chains.BTC


def build_address_list(balance_tracked: list, bond_tracked: list) -> dict:
    balance_tracked, bond_tracked = set(balance_tracked), set(bond_tracked)

    def sort_key(a):
        return CHAIN_ORDER.get(detect_chain(a), 9), a

    addresses = {}
    for address in sorted(balance_tracked, key=sort_key):
        addresses[address] = {
            Props.PROP_CHAIN: detect_chain(address),
            Props.PROP_TRACK_BALANCE: True,
            Props.PROP_MIN_LIMIT: 0,
            Props.PROP_TRACK_BOND: address in bond_tracked,
        }
    for address in sorted(bond_tracked - balance_tracked, key=sort_key):
        addresses[address] = {
            Props.PROP_CHAIN: detect_chain(address),
            Props.PROP_TRACK_BALANCE: False,
            Props.PROP_MIN_LIMIT: 0,
            Props.PROP_TRACK_BOND: True,
        }
    return addresses


async def restore(app: LpAppFramework, user_id: str, apply: bool, force: bool):
    manager: SettingsManager = app.deps.settings_manager
    db = app.deps.db

    settings = await manager.get_settings(user_id)
    sep(f'Current settings of {user_id}')
    print(json.dumps(settings, indent=2))

    current = (settings.get(GeneralSettings.BALANCE_TRACK) or {}).get(Props.KEY_ADDRESSES) or {}
    if current and not force:
        print(f'\nThe list already has {len(current)} addresses. Nothing to do (use --force to overwrite).')
        return

    balance_tracked = await WalletWatchlist(db).all_nodes_for_user(user_id)
    bond_tracked = await BondWatchlist(db).all_nodes_for_user(user_id)
    addresses = build_address_list(balance_tracked, bond_tracked)

    sep('Restored list')
    for i, (address, obj) in enumerate(addresses.items(), start=1):
        flags = ('balance ' if obj[Props.PROP_TRACK_BALANCE] else '') + ('bond' if obj[Props.PROP_TRACK_BOND] else '')
        print(f'{i:3d}. {obj[Props.PROP_CHAIN]:5s} {address}  [{flags.strip()}]')
    print(f'Total: {len(addresses)} addresses, {len(set(balance_tracked))} with balance tracking')

    if not addresses:
        print('Nothing to restore: both watch sets are empty.')
        return

    if not apply:
        print('\nDry run. Re-run with --apply to write.')
        return

    backup_file = f'settings_backup_{user_id}_{int(time.time())}.json'
    with open(backup_file, 'w') as f:
        json.dump(settings, f)
    print(f'Previous record saved to {backup_file}')

    settings.setdefault(GeneralSettings.BALANCE_TRACK, {})[Props.KEY_ADDRESSES] = addresses
    await manager.set_settings(user_id, settings)

    check = await manager.get_settings(user_id)
    restored = check[GeneralSettings.BALANCE_TRACK][Props.KEY_ADDRESSES]
    sep('Done')
    print(f'Written: {len(restored)} addresses. Other keys kept: {sorted(k for k in check if k != GeneralSettings.BALANCE_TRACK)}')


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('user_id', help='Telegram user id (the settings channel id)')
    parser.add_argument('--apply', action='store_true', help='write the list (default: dry run)')
    parser.add_argument('--force', action='store_true', help='overwrite a non-empty list')
    # older builds read the config path from the first argument unconditionally: let it pass through Config
    # (python tools/restore_wallet_list.py /config/config.yaml <user_id>) and keep it out of our own arguments
    own_args = [a for a in sys.argv[1:] if not a.lower().endswith(('.yaml', '.yml'))]
    args = parser.parse_args(own_args)

    app = LpAppFramework(log_level=logging.WARNING)
    async with app:
        await restore(app, str(args.user_id), apply=args.apply, force=args.force)


if __name__ == '__main__':
    asyncio.run(main())
