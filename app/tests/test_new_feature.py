from datetime import datetime

from services.lib.new_feature import NewFeatureManager


class TestF:
    EXPIRE_TABLE = {
        'Test.Old': datetime(2022, 2, 24),
        'Test.New': datetime(2042, 2, 24),

        'Deep.Feature.Hidden.Some.Where': datetime(2030, 12, 31)
    }


def test_new_1():
    ref = datetime(2022, 5, 29)

    nfm = NewFeatureManager(TestF.EXPIRE_TABLE)
    assert not nfm.is_new('Test.Old', ref)
    assert nfm.is_new('Test.New', ref)
    assert nfm.is_new('Test', ref)
    assert not nfm.is_new('No', ref)

    assert nfm.is_new('Deep', ref)
    assert nfm.is_new('Deep.Feature', ref)
    assert nfm.is_new('Deep.Feature.Hidden', ref)
    assert nfm.is_new('Deep.Feature.Hidden.Some', ref)
    assert nfm.is_new('Deep.Feature.Hidden.Some.Where', ref)
    assert not nfm.is_new('Deep.Feature.Surprise', ref)

    NEW = '🆕'
    assert nfm.new_sing('Test.Old', ref) == ''
    assert nfm.new_sing('Test.New', ref) == NEW
    assert nfm.new_sing('Test', ref) == NEW
    assert nfm.new_sing('Test', ref) == NEW
    assert nfm.new_sing('No', ref) == ''
    assert nfm.new_sing('Deep.Feature', ref) == NEW
