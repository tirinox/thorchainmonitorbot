import json
from pathlib import Path

import pytest

from api.aionode.types import ThorConstants, ThorMimir
from models.mimir import MimirHolder, MimirTuple
from models.mimir_naming import MIMIR_DICT_FILENAME, MimirNameRules


SAMPLE_DATA = Path(__file__).parent / 'sample_data'


def load_json(name):
    with (SAMPLE_DATA / name).open() as file:
        return json.load(file)


@pytest.fixture(scope='module')
def current_rules():
    constants = load_json('mimir_constants_current.json')
    constant_names = [name for values in constants.values() for name in values]

    rules = MimirNameRules()
    rules.load(MIMIR_DICT_FILENAME)
    rules.learn_canonical_names(constant_names)
    return rules


def test_camel_case_parser_preserves_protocol_acronyms_and_numbers():
    split = MimirNameRules._split_camel_case

    assert split('L1DynamicFeeCeilingBPS') == ['L1', 'Dynamic', 'Fee', 'Ceiling', 'BPS']
    assert split('RUNEPoolEnabled') == ['RUNE', 'Pool', 'Enabled']
    assert split('TCYStakeDistributionHalt') == ['TCY', 'Stake', 'Distribution', 'Halt']
    assert split('MaxUTXOsToSpend') == ['Max', 'UTXOs', 'To', 'Spend']


def test_all_current_constants_get_nonempty_human_titles(current_rules):
    constants = load_json('mimir_constants_current.json')
    constant_names = [name for values in constants.values() for name in values]

    assert len(constant_names) >= 170
    for name in constant_names:
        title = current_rules.name_to_human(name)
        assert title
        assert '?' not in title
        assert title != name.upper()


@pytest.mark.parametrize(('name', 'expected'), [
    ('AdvSwapQueueRapidSwapMax', 'Advanced Swap Queue Rapid Swap Max'),
    ('L1DynamicFeeCeilingBPS', 'L1 Dynamic Fee Ceiling BPS'),
    ('MaxDepositTxIDRetries', 'Max Deposit Tx ID Retries'),
    ('RUNEPoolMaxReserveBackstop', 'RUNE Pool Max Reserve Backstop'),
    ('WasmArbSlipMinBps', 'Wasm Arb Slip Min BPS'),
    ('FeeUSDRoundSignificantDigits', 'Fee USD Round Significant Digits'),
    ('TCYStakeSystemIncomeBps', 'TCY Stake System Income BPS'),
])
def test_representative_current_constant_titles(current_rules, name, expected):
    assert current_rules.name_to_human(name) == expected
    assert current_rules.name_to_human(name.upper()) == expected


def test_all_current_mimirs_are_decoded_without_unknown_fragments(current_rules):
    mimir = load_json('mimir_current.json')

    assert len(mimir) >= 250
    for name in mimir:
        title = current_rules.name_to_human(name)
        assert title
        assert title != name
        assert '?' not in title
        assert not {'ATURE', 'RESH', 'LIP'} & set(title.split())


def test_holder_learns_constants_before_building_all_current_entries():
    holder = MimirHolder()
    holder.mimir_rules.load(MIMIR_DICT_FILENAME)
    holder.update(
        MimirTuple(
            constants=ThorConstants.from_json(load_json('mimir_constants_current.json')),
            mimir=ThorMimir.from_json(load_json('mimir_current.json')),
            node_mimir={},
            votes=[],
            thor_height=1,
            ts=1.0,
        ),
        active_nodes=[],
    )

    assert len(holder.all_entries) >= 360
    assert holder.pretty_name('SIGNATUREREFRESHBLOCKS') == 'Signature Refresh Blocks'
    assert holder.pretty_name('WASMARBSLIPMINBPS') == 'Wasm Arb Slip Min BPS'
    assert all(entry.pretty_name and '?' not in entry.pretty_name for entry in holder.all_entries)


@pytest.mark.parametrize(('name', 'expected'), [
    ('ADR029', 'ADR-29'),
    ('ADR031', 'ADR-31'),
    ('SIGNATUREREFRESHBLOCKS', 'Signature Refresh Blocks'),
    ('PREFERREDASSETOUTBOUNDFEEMULTIPLIER', 'Preferred Asset Outbound Fee Multiplier'),
    ('SECUREDASSETSLIPMINBPS', 'Secured Asset Slip Min BPS'),
    ('DYNAMICFEE-WHITELIST-SS', 'Dynamic Fee Whitelist SS'),
    ('DYNAMICFEE-WHITELIST-SYMBIOSIS', 'Dynamic Fee Whitelist Symbiosis'),
    ('ENABLESWITCH-GAIA-XUSK', 'Enable Switch Gaia XUSK'),
    ('HALTWASMCONTRACT-YEVLEC', 'Halt Wasm Contract YEVLEC'),
    ('HALTTRRONTRADING', 'Halt TRON Trading'),
    ('PAUSELPDEPOSIT-AVAX-USDC-0XB97EF9EF8734C71904D8002F8B6BC66DD9C48A6E',
     'Pause LP Deposit AVAX.USDC'),
    ('SOLVENCYHALTVAULT-THORPUB1ADDWNPEPQ2W263PPN263CGJTJY583G0QSX3GDWQ0QEE304CFM8V03HZX86KVVQVE29D-AVAX',
     'Solvency Halt Vault THORPUB1AD...E29D AVAX'),
    ('SOLVENCYHALTVAULT-THORPUB1ADDWNPEPQWHQW3MRGEPFURQT497XRRPXD4U89Y6P5EV6KM7AY4FK82Z4P6XNCAV37HT-SOL',
     'Solvency Halt Vault THORPUB1AD...37HT SOL'),
])
def test_tricky_current_mimir_titles(current_rules, name, expected):
    assert current_rules.name_to_human(name) == expected


@pytest.mark.parametrize(('name', 'expected'), [
    ('ADR032', 'ADR-32'),
    ('MAXOBSERVATIONDELAYBLOCKS', 'Max Observation Delay Blocks'),
    ('ENABLECROSSCHAINSWAPS', 'Enable Cross Chain Swaps'),
    ('MINIMUMSECURITYBUFFERBASISPOINTS', 'Minimum Security Buffer Basis Points'),
    ('DYNAMICFEE-WHITELIST-NEWPROTOCOL', 'Dynamic Fee Whitelist New Protocol'),
    ('STREAMINGSWAPMAXATTEMPTS', 'Streaming Swap Max Attempts'),
    ('HALTWASMCONTRACT-ABC123', 'Halt Wasm Contract ABC123'),
    ('ENABLESWITCH-GAIA-XYZ', 'Enable Switch Gaia XYZ'),
    ('PAUSELPDEPOSIT-BASE-NEWTOKEN-0X0123456789ABCDEF0123456789ABCDEF01234567',
     'Pause LP Deposit BASE.NEWTOKEN'),
    ('TORANCHOR-BASE-NEWUSD-0X0123456789ABCDEF0123456789ABCDEF01234567',
     'TOR Anchor BASE.NEWUSD'),
])
def test_plausible_future_mimir_titles(current_rules, name, expected):
    assert current_rules.name_to_human(name) == expected


def test_yaml_translation_remains_authoritative(current_rules):
    assert current_rules.name_to_human('ADR021') == 'ADR-21 Marketing Budget'
    assert current_rules.name_to_human('HALTTRADING') == 'Halt All Trading'
