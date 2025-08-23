from lib.date_utils import DAY
from lib.depcont import DepContainer
from lib.logs import WithLogger
from lib.utils import safe_get


class ArbStatus:
    UNKNOWN = 'UNKNOWN'
    ARB = 'ARB'
    NOT_ARB = 'NOT_ARB'
    ERROR = 'ERROR'


class ArbBotDetector(WithLogger):
    NAME_PREFIX = 'Arb-Bot-'

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.min_sequence = deps.cfg.as_int('names.arb_bot_detector.min_sequence', 1000)
        self.logger.info(f'Arb bot detector min sequence: {self.min_sequence}')
        self.mark_expiration = deps.cfg.as_int('names.arb_bot_detector.mark_expiration', 7 * DAY)

    @staticmethod
    def _key(address: str) -> str:
        return f'ArbBot:{address}'

    async def read_arb_status(self, address: str) -> str:
        r = await self.deps.db.get_redis()
        status = await r.get(self._key(address))
        return status or ArbStatus.UNKNOWN

    async def is_marked_as_arb(self, address: str) -> bool:
        return (await self.read_arb_status(address)) == ArbStatus.ARB

    async def mark_as_arb(self, address: str, status: str = ArbStatus.ARB):
        r = await self.deps.db.get_redis()
        await r.set(self._key(address), status, ex=self.mark_expiration)

    async def try_to_detect_arb_bot(self, address: str):
        """
        Try to detect if the address is an arb bot.
        Safe function, doesn't raise exceptions.
        @param address:
        @return:
        """
        try:
            status = await self.read_arb_status(address)
            if status == ArbStatus.UNKNOWN:
                is_arb = await self._is_detect_arb_bot(address)
                await self.register_new_arb_bot(address, is_arb)
            return status
        except Exception as e:
            self.logger.exception(f'Error: {e}')
            return ArbStatus.UNKNOWN

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

    async def register_new_arb_bot(self, address: str, is_arb: bool):
        if not is_arb:
            name = self.NAME_PREFIX + address[-4:]
            await self.deps.name_service.cache.save_custom_name(name, address, expiring=False)
            await self.deps.name_service.cache.save_name_list(address, [name], expiring=False)
        await self.mark_as_arb(address, ArbStatus.ARB if is_arb else ArbStatus.NOT_ARB)

    def is_arb_name(self, name: str):
        return name.startswith(self.NAME_PREFIX)
