import logging
from contextlib import ExitStack, AsyncExitStack
from io import BytesIO

from PIL import Image
from aiogram.types import User, Message, PhotoSize

from localization import BaseLocalization
from services.dialog.stake_info import LOADING_STICKER
from services.lib.plot_graph import img_to_bio
from services.lib.utils import async_wrap


async def get_userpic(user: User) -> Image:
    pics = await user.get_profile_photos(0, 1)
    if pics.photos and pics.photos[0]:
        first_pic: PhotoSize = pics.photos[0][0]
        photo_raw = BytesIO()
        await first_pic.download(destination=photo_raw)
        return Image.open(photo_raw)


async def handle_avatar_picture(message: Message, loc: BaseLocalization):
    # POST A LOADING STICKER
    async with AsyncExitStack() as stack:
        sticker = await message.answer_sticker(LOADING_STICKER, disable_notification=True)
        stack.push_async_callback(sticker.delete)

        user_pic: Image.Image = await get_userpic(message.from_user)
        if user_pic is None:
            await message.reply('⚠️ You have no userpic...')

        w, h = user_pic.size
        if w != h:
            await message.reply('🖼️ Your userpic is not square')
            return

        if not w or not h:
            await message.reply('⚠️ Your userpic is invalid')
            return

        pic = await combine_frame_and_photo(user_pic)
        pic = img_to_bio(pic, name='thor_ava.png')
        # await message.reply_photo(pic, caption='Your THORChain avatar is ready!')
        await message.reply_document(pic, caption='Your THORChain avatar is ready!')


THOR_AVA_FRAME_PATH = './data/thor_ava_frame.png'


@async_wrap
def combine_frame_and_photo(photo: Image.Image):
    frame = Image.open(THOR_AVA_FRAME_PATH)

    photo = photo.resize(frame.size).convert('RGBA')
    result = Image.alpha_composite(photo, frame)

    return result
