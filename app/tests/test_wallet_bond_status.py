from comm.localization.eng_base import BaseLocalization
from lib.config import Config
from lib.constants import THOR_BLOCK_TIME
from lib.date_utils import seconds_human
from models.node_info import BondProvider, NodeInfo


def test_bond_provision_shows_node_state_and_duration():
    localization = BaseLocalization(Config(data={}))
    active_node = NodeInfo(status=NodeInfo.ACTIVE, node_address='thor-active', status_since=100)
    inactive_node = NodeInfo(status=NodeInfo.STANDBY, node_address='thor-inactive', status_since=80)
    bonds = [
        (active_node, BondProvider('provider-active', 1)),
        (inactive_node, BondProvider('provider-inactive', 2)),
    ]

    text = localization.text_bond_provision(
        bonds,
        usd_per_rune=1,
        current_block_height=110,
    )

    assert f'active for ≈ {seconds_human(10 * THOR_BLOCK_TIME)}' in text
    assert f'inactive for ≈ {seconds_human(30 * THOR_BLOCK_TIME)}' in text


def test_bond_provision_reports_missing_node_state_age():
    localization = BaseLocalization(Config(data={}))
    node = NodeInfo(status=NodeInfo.ACTIVE, node_address='thor-active')

    text = localization.text_bond_provision(
        [(node, BondProvider('provider-active', 1))],
        usd_per_rune=1,
        current_block_height=110,
    )

    assert 'active (state age unavailable)' in text
