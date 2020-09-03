import asyncio
import logging

from aiogram.utils import exceptions

log = logging.getLogger('broadcast')


async def send_message(bot, user_id: int, text: str, disable_notification: bool = False) -> bool:
    """
    Safe messages sender
    :param user_id:
    :param text:
    :param disable_notification:
    :return:
    """
    try:
        await bot.send_message(user_id, text,
                               disable_notification=disable_notification,
                               disable_web_page_preview=True)
    except exceptions.BotBlocked:
        log.error(f"Target [ID:{user_id}]: blocked by user")
    except exceptions.ChatNotFound:
        log.error(f"Target [ID:{user_id}]: invalid user ID")
    except exceptions.RetryAfter as e:
        log.error(f"Target [ID:{user_id}]: Flood limit is exceeded. Sleep {e.timeout} seconds.")
        await asyncio.sleep(e.timeout)
        return await send_message(bot, user_id, text)  # Recursive call
    except exceptions.UserDeactivated:
        log.error(f"Target [ID:{user_id}]: user is deactivated")
    except exceptions.TelegramAPIError:
        log.exception(f"Target [ID:{user_id}]: failed")
        return True  # tg error is not the reason to exlude the user
    else:
        log.info(f"Target [ID:{user_id}]: success")
        return True
    return False


async def broadcaster(bot, user_ids, message) -> (int, list, list):
    """
    Simple broadcaster
    :return: Count of messages and good and bad ids
    """
    count = 0
    good_ones, bad_ones = [], []

    try:
        for user_id in user_ids:
            if await send_message(bot, user_id, message):
                count += 1
                good_ones.append(user_id)
            else:
                bad_ones.append(user_id)
            await asyncio.sleep(.05)  # 20 messages per second (Limit: 30 messages per second)
    finally:
        log.info(f"{count} messages successful sent.")

    return count, good_ones, bad_ones