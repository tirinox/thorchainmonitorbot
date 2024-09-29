from datetime import datetime


class Features:
    F_SETTINGS = 'Settings'
    F_MY_WALLETS = 'MyWallets'

    F_PERSONAL_PRICE_DIV = 'Settings.PriceDivergence'
    F_PERSONAL_TRACK_BALANCE = 'MyWallets.TrackBalance'
    F_PERSONAL_TRACK_BALANCE_LIMIT = 'MyWallets.SetLimit'

    F_BOND_PROVIDER = 'MyWallets.BondProvider'

    F_TEST_EXPIRED = 'Test.Expired'
    F_TEST_NOT_EXPIRED = 'Test.NotExpired'
    F_WALLET_SETTINGS = 'MyWallets.WalletSettings'

    EXPIRE_TABLE = {
        F_PERSONAL_PRICE_DIV: datetime(2022, 8, 12),
        F_PERSONAL_TRACK_BALANCE: datetime(2022, 9, 10),
        F_PERSONAL_TRACK_BALANCE_LIMIT: datetime(2022, 10, 10),

        F_BOND_PROVIDER: datetime(2024, 2, 1),
        F_WALLET_SETTINGS: datetime(2024, 4, 1),

        F_TEST_EXPIRED: datetime(2022, 2, 24),
        F_TEST_NOT_EXPIRED: datetime(2042, 2, 24),
    }


class NewFeatureManager:
    def __init__(self, expire_table: dict):
        self._expire_table_final = {}
        self.build_tree(expire_table)

    def build_tree(self, expire_table):
        table = self._expire_table_final
        for attr, date in expire_table.items():
            components = attr.split('.')
            for last_component_index in range(1, len(components)):
                sub_key = '.'.join(components[:last_component_index])
                table[sub_key] = max(date, table.get(sub_key, date))
        # original expire dates
        self._expire_table_final.update(expire_table)

    def is_new(self, key, ref=None):
        expire_data = self._expire_table_final.get(key)
        if not expire_data:
            return False
        now = ref or datetime.now()
        return now <= expire_data

    def new_sing(self, key, ref=None):
        return self.sign(self.is_new(key, ref))

    @staticmethod
    def sign(value):
        return '🆕' if value else ''
