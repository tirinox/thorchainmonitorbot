from services.lib.new_feature import NewFeatureManager, Features


def test_new_1():
    nfm = NewFeatureManager()
    assert not nfm.is_new(Features.TEST_EXPIRED)
    assert nfm.is_new(Features.TEST_NOT_EXPIRED)

    assert (nfm.is_new(Features.TEST_EXPIRED, True) == '')
    assert (nfm.is_new(Features.TEST_NOT_EXPIRED, True) == '🆕')
