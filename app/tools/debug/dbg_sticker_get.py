import asyncio

from aiogram import Bot
from aiogram.types import ParseMode

from services.lib.config import Config


async def main():
    cfg = Config()
    sticker = cfg.cap.raised.stickers[0]
    print(f'{sticker = }')
    bot = Bot(token=cfg.telegram.bot.token, parse_mode=ParseMode.HTML)
    file = await bot.get_file(sticker)
    print(file)
    bio_data = await bot.download_file(file['file_path'])

    with open('./data/temp.webp', 'wb') as f:
        data = bio_data.read()
        print(data)
        f.write(data)


if __name__ == '__main__':
    asyncio.run(main())