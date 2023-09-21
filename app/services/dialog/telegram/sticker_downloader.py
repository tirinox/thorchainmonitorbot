import os

from PIL import Image
from aiogram import Bot

from services.lib.draw_utils import img_to_bio
from services.lib.utils import hash_of_string_repr


class TelegramStickerDownloader:
    def __init__(self, bot: Bot, base_path='./data/stickers'):
        self.base_path = base_path
        self.bot = bot

    def sticker_local_path(self, sticker_id):
        hashed = hash_of_string_repr(sticker_id)
        return os.path.join(self.base_path, f'tg-sticker-{hashed}.webp')

    async def _download_sticker(self, sticker_id, target_path):
        file = await self.bot.get_file(sticker_id)
        bio_data = await self.bot.download_file(file['file_path'])
        with open(target_path, 'wb') as f:
            data = bio_data.read()
            f.write(data)

    async def get_sticker_image(self, sticker_id) -> Image.Image:
        local_path = self.sticker_local_path(sticker_id)
        if not os.path.exists(local_path):
            await self._download_sticker(sticker_id, local_path)
        sticker = Image.open(local_path).convert("RGBA")
        return sticker

    async def get_sticker_image_bio(self, sticker_id, filename='sticker.png') -> Image.Image:
        sticker = await self.get_sticker_image(sticker_id)
        return img_to_bio(sticker, filename)
