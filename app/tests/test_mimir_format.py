from comm.localization.eng_base import EnglishLocalization
from models.mimir_naming import MimirUnits


def test_format_mimir_bool_only_one_is_yes():
    loc = EnglishLocalization(object())

    assert loc.format_mimir_value('TEST_MIMIR', 1, MimirUnits.UNITS_BOOL) == loc.MIMIR_YES
    assert loc.format_mimir_value('TEST_MIMIR', '1', MimirUnits.UNITS_BOOL) == loc.MIMIR_YES

    assert loc.format_mimir_value('TEST_MIMIR', 0, MimirUnits.UNITS_BOOL) == '0'
    assert loc.format_mimir_value('TEST_MIMIR', 2, MimirUnits.UNITS_BOOL) == '2'
    assert loc.format_mimir_value('TEST_MIMIR', '0', MimirUnits.UNITS_BOOL) == '0'
    assert loc.format_mimir_value('TEST_MIMIR', 'unexpected', MimirUnits.UNITS_BOOL) == 'unexpected'

