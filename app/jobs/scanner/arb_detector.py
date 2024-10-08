from lib.depcont import DepContainer
from lib.logs import WithLogger
from lib.utils import safe_get


class ArbBotDetector(WithLogger):
    NAME_PREFIX = 'Arb-Bot-'

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.min_sequence = deps.cfg.as_int('names.arb_bot_detector.min_sequence', 1000)
        self.logger.info(f'Arb bot detector min sequence: {self.min_sequence}')

    async def try_to_detect_arb_bot(self, address: str):
        """
        Try to detect if the address is an arb bot.
        Safe function, doesn't raise exceptions.
        @param address:
        @return:
        """
        try:
            name = await self.deps.name_service.lookup_name_by_address(address)
            if name:
                return self.is_arb_name(name.name)

            is_arb = await self._is_detect_arb_bot(address)
            if is_arb:
                await self.register_new_arb_bot(address)
            return is_arb
        except Exception as e:
            self.logger.exception(f'Error in try_to_detect_arb_bot: {e}')
            return False

    async def _is_detect_arb_bot(self, address) -> bool:
        if not address:
            self.logger.error('Empty address')
            return False

        account = await self.deps.thor_connector.query_raw(f'/cosmos/auth/v1beta1/accounts/{address}')
        if not account:
            self.logger.error(f'Empty account for {address}')
            return False

        sequence = safe_get(account, 'account', 'sequence')
        sequence = int(sequence)
        if sequence >= self.min_sequence:
            return True

        return False

    async def register_new_arb_bot(self, address: str):
        name = self.NAME_PREFIX + address[-4:]
        await self.deps.name_service.cache.save_custom_name(name, address, expiring=False)
        await self.deps.name_service.cache.save_name_list(address, [name], expiring=False)

    def is_arb_name(self, name: str):
        return name.startswith(self.NAME_PREFIX)
