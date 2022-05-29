from datetime import datetime


class Features:
    PERSONAL_PRICE_DIV = 'pers_price_div'

    TEST_EXPIRED = 'test_expired'
    TEST_NOT_EXPIRED = 'test_not_expired'

    EXPIRE_TABLE = {
        PERSONAL_PRICE_DIV: datetime(2022, 6, 12),

        TEST_EXPIRED: datetime(2022, 2, 24),
        TEST_NOT_EXPIRED: datetime(2042, 2, 24),
    }


class NewFeatureManager:
    def is_new(self, key, new_sign=False):
        expire_data = Features.EXPIRE_TABLE.get(key)
        if not expire_data:
            return False
        now = datetime.now()
        is_new = now <= expire_data
        return self.sign(is_new) if new_sign else is_new

    @staticmethod
    def sign(value):
        return '🆕' if value else ''
