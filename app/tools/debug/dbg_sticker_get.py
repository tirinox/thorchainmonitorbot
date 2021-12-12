import asyncio

from aiogram import Bot
from aiogram.types import ParseMode

from services.lib.config import Config
from services.lib.telegram import TelegramStickerDownloader


async def primitive(sticker_id, bot):
    file = await bot.get_file(sticker_id)
    print(file)
    bio_data = await bot.download_file(file['file_path'])

    with open('./data/temp.webp', 'wb') as f:
        data = bio_data.read()
        print(data)
        f.write(data)


async def advanced_test(sticker_id, bot):
    dl = TelegramStickerDownloader(bot)
    p = await dl.get_sticker_image(sticker_id)
    p.show()


async def main():
    cfg = Config()
    sticker = cfg.cap.raised.stickers[0]
    print(f'{sticker = }')
    bot = Bot(token=cfg.telegram.bot.token, parse_mode=ParseMode.HTML)
    await advanced_test(sticker, bot)


if __name__ == '__main__':
    asyncio.run(main())
