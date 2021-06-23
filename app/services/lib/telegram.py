import urllib.parse

import aiohttp


def to_json_bool(b):
    return 'true' if b else 'false'


async def telegram_send_message_basic(bot_token, user_id, message_text: str,
                                      disable_web_page_preview=True,
                                      disable_notification=True):
    message_text = message_text.strip()

    if not message_text:
        return

    message_text = urllib.parse.quote_plus(message_text)
    url = (
        f"https://api.telegram.org/"
        f"bot{bot_token}/sendMessage?"
        f"chat_id={user_id}&"
        f"text={message_text}&"
        f"parse_mode=HTML&"
        f"disable_web_page_preview={to_json_bool(disable_web_page_preview)}&"
        f"disable_notification={to_json_bool(disable_notification)}"
    )

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                err = await resp.read()
                raise Exception(f'Telegram error: "{err}"')
            return resp.status == 200
