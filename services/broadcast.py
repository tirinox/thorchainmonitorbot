import asyncio
import logging

from aiogram.utils import exceptions

log = logging.getLogger('broadcast')


async def send_message(bot, chat_id: int, text: str, disable_notification: bool = False) -> bool:
    """
    Safe messages sender
    :param chat_id:
    :param text:
    :param disable_notification:
    :return:
    """
    try:
        await bot.send_message(chat_id, text,
                               disable_notification=disable_notification,
                               disable_web_page_preview=True)
    except exceptions.BotBlocked:
        log.error(f"Target [ID:{chat_id}]: blocked by user")
    except exceptions.ChatNotFound:
        log.error(f"Target [ID:{chat_id}]: invalid user ID")
    except exceptions.RetryAfter as e:
        log.error(f"Target [ID:{chat_id}]: Flood limit is exceeded. Sleep {e.timeout} seconds.")
        await asyncio.sleep(e.timeout)
        return await send_message(bot, chat_id, text)  # Recursive call
    except exceptions.UserDeactivated:
        log.error(f"Target [ID:{chat_id}]: user is deactivated")
    except exceptions.TelegramAPIError:
        log.exception(f"Target [ID:{chat_id}]: failed")
        return True  # tg error is not the reason to exlude the user
    else:
        log.info(f"Target [ID:{chat_id}]: success")
        return True
    return False


async def broadcaster(bot, chat_ids, message, delay=0.1) -> (int, list, list):
    """
    Simple broadcaster
    :return: Count of messages and good and bad ids
    """
    count = 0
    good_ones, bad_ones = [], []
    chat_ids = list(chat_ids)

    try:
        for chat_id in chat_ids:
            if isinstance(message, str):
                final_message = message
            else:
                final_message = await message(chat_id)
            if await send_message(bot, chat_id, final_message):
                count += 1
                good_ones.append(chat_id)
            else:
                bad_ones.append(chat_id)
            await asyncio.sleep(delay)  # 10 messages per second (Limit: 30 messages per second)
    finally:
        log.info(f"{count} messages successful sent (of {len(chat_ids)})")

    return count, good_ones, bad_ones
