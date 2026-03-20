from comm.localization.eng_base import EnglishLocalization
from lib.config import Config
from models.mimir_naming import MimirUnits, MimirNameRules, MIMIR_DICT_FILENAME


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


