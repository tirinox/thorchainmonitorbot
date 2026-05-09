from comm.localization.eng_base import EnglishLocalization
from lib.config import Config
from lib.texts import shorten_text
from models.mimir import AlertMimirVoting, MimirVoting, MIMIR_VOTING_KEY_DISPLAY_LIMIT
from models.mimir import MimirHolder
from models.mimir_naming import MimirUnits, MimirNameRules, MIMIR_DICT_FILENAME
from typing import cast


def make_loc():
    return EnglishLocalization(Config(name='./tests/test_config.yaml'))


def test_format_mimir_bool_only_one_is_yes():
    loc = make_loc()

    assert loc.format_mimir_value('TEST_MIMIR', 1, MimirUnits.UNITS_BOOL) == loc.MIMIR_YES
    assert loc.format_mimir_value('TEST_MIMIR', '1', MimirUnits.UNITS_BOOL) == loc.MIMIR_YES

    assert loc.format_mimir_value('TEST_MIMIR', 0, MimirUnits.UNITS_BOOL) == '0'
    assert loc.format_mimir_value('TEST_MIMIR', 2, MimirUnits.UNITS_BOOL) == '2'
    assert loc.format_mimir_value('TEST_MIMIR', '0', MimirUnits.UNITS_BOOL) == '0'
    assert loc.format_mimir_value('TEST_MIMIR', 'unexpected', MimirUnits.UNITS_BOOL) == 'unexpected'


def test_format_mimir_vote_for_against():
    loc = make_loc()

    assert loc.format_mimir_value('ADR024', 1, MimirUnits.UNITS_VOTE_FOR_AGAINST) == loc.MIMIR_VOTE_FOR
    assert loc.format_mimir_value('ADR024', '1', MimirUnits.UNITS_VOTE_FOR_AGAINST) == loc.MIMIR_VOTE_FOR

    assert loc.format_mimir_value('ADR024', 0, MimirUnits.UNITS_VOTE_FOR_AGAINST) == loc.MIMIR_VOTE_AGAINST
    assert loc.format_mimir_value('ADR024', '0', MimirUnits.UNITS_VOTE_FOR_AGAINST) == loc.MIMIR_VOTE_AGAINST

    assert loc.format_mimir_value('ADR024', 2, MimirUnits.UNITS_VOTE_FOR_AGAINST) == '2'
    assert loc.format_mimir_value('ADR024', 'unexpected', MimirUnits.UNITS_VOTE_FOR_AGAINST) == 'unexpected'


def test_adr_keys_use_vote_for_against_units():
    rules = MimirNameRules()
    rules.load(MIMIR_DICT_FILENAME)

    assert rules.get_mimir_units('ADR024') == MimirUnits.UNITS_VOTE_FOR_AGAINST
    assert rules.get_mimir_units('adr024') == MimirUnits.UNITS_VOTE_FOR_AGAINST

    loc = make_loc()
    loc.mimir_rules = rules

    assert loc.format_mimir_value('ADR024', '1') == loc.MIMIR_VOTE_FOR
    assert loc.format_mimir_value('ADR024', '0') == loc.MIMIR_VOTE_AGAINST


class _DummyMimirRules:
    @staticmethod
    def get_mimir_units(_key):
        return None


class _DummyHolder:
    mimir_rules = _DummyMimirRules()

    @staticmethod
    def get_entry(_key):
        return None

    @staticmethod
    def pretty_name(key):
        return key


def test_alert_mimir_voting_to_dict_keeps_raw_key_and_adds_truncated_display_key():
    key = 'ARTIFICIALRAGNAROKBLOCKHEIGHT'
    alert = AlertMimirVoting(
        holder=cast(MimirHolder, cast(object, _DummyHolder())),
        voting=MimirVoting(key, {}, 100),
    )

    data = alert.to_dict(loc=None)

    assert data['key'] == key
    assert data['key_display'] == shorten_text(key, MIMIR_VOTING_KEY_DISPLAY_LIMIT)
    assert len(data['key_display']) == MIMIR_VOTING_KEY_DISPLAY_LIMIT


def test_alert_mimir_voting_to_dict_does_not_change_short_display_key():
    key = 'NEXTCHAIN'
    alert = AlertMimirVoting(
        holder=cast(MimirHolder, cast(object, _DummyHolder())),
        voting=MimirVoting(key, {}, 100),
    )

    data = alert.to_dict(loc=None)

    assert data['key'] == key
    assert data['key_display'] == key


