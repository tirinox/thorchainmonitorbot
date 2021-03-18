import asyncio
from contextlib import AsyncExitStack
from io import BytesIO

from PIL import Image
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.dispatcher.storage import FSMContextProxy
from aiogram.types import User, Message, PhotoSize, ReplyKeyboardRemove
from aiogram.types.mixins import Downloadable
from aiogram.utils.helper import HelperMode

from localization import BaseLocalization
from services.dialog.base import BaseDialog, message_handler
from services.dialog.picture.avatar import image_square_crop, combine_frame_and_photo, make_avatar
from services.dialog.stake_info_dialog import LOADING_STICKER, ContentTypes
from services.lib.depcont import DepContainer
from services.lib.plot_graph import img_to_bio
from services.lib.texts import kbd


async def download_tg_photo(photo: Downloadable) -> Image.Image:
    photo_raw = BytesIO()
    await photo.download(destination=photo_raw)
    return Image.open(photo_raw)


async def get_userpic(user: User) -> Image.Image:
    pics = await user.get_profile_photos(0, 1)
    if pics.photos and pics.photos[0]:
        first_pic: PhotoSize = pics.photos[0][0]
        return await download_tg_photo(first_pic)


class AvatarStates(StatesGroup):
    mode = HelperMode.snake_case
    MAIN = State()


class AvatarDialog(BaseDialog):
    def __init__(self, loc: BaseLocalization, data: FSMContextProxy, d: DepContainer):
        super().__init__(loc, data, d)
        self._work_lock = asyncio.Lock()

    def menu_kbd(self):
        return kbd([
            self.loc.BUTTON_AVA_FROM_MY_USERPIC,
            self.loc.BUTTON_SM_BACK_MM,
        ], vert=True)

    @message_handler(state=AvatarStates.MAIN)
    async def on_enter(self, message: Message):
        if message.text == self.loc.BUTTON_SM_BACK_MM:
            await self.go_back(message)
        elif message.text == self.loc.BUTTON_AVA_FROM_MY_USERPIC:
            await self.handle_avatar_picture(message, self.loc)
        else:
            await AvatarStates.MAIN.set()
            await message.reply(self.loc.TEXT_AVA_WELCOME, reply_markup=self.menu_kbd())

    @message_handler(state=AvatarStates.MAIN, content_types=ContentTypes.PHOTO)
    async def on_picture(self, message: Message):
        await self.handle_avatar_picture(message, self.loc, explicit_picture=message.photo[0])

    @message_handler(state=AvatarStates.MAIN, content_types=ContentTypes.DOCUMENT)
    async def on_picture_doc(self, message: Message):
        await self.handle_avatar_picture(message, self.loc, explicit_picture=message.document)

    async def handle_avatar_picture(self, message: Message, loc: BaseLocalization,
                                    explicit_picture: Downloadable = None):
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(self._work_lock)

            # POST A LOADING STICKER
            sticker = await message.answer_sticker(LOADING_STICKER,
                                                   disable_notification=True,
                                                   reply_markup=ReplyKeyboardRemove())
            # CLEAN UP IN THE END
            stack.push_async_callback(sticker.delete)

            try:
                if explicit_picture is not None:
                    user_pic = await download_tg_photo(explicit_picture)
                else:
                    user_pic = await get_userpic(message.from_user)
            except Exception:
                await message.reply(loc.TEXT_AVA_ERR_INVALID, reply_markup=self.menu_kbd())
                return

            if user_pic is None:
                await message.reply(loc.TEXT_AVA_ERR_NO_PIC, reply_markup=self.menu_kbd())
                return

            w, h = user_pic.size
            if not w or not h:
                await message.reply(loc.TEXT_AVA_ERR_INVALID, reply_markup=self.menu_kbd())
                return

            pic = await make_avatar(user_pic, with_lasers=True)

            user_id = message.from_user.id
            pic = img_to_bio(pic, name=f'thor_ava_{user_id}.png')
            await message.reply_document(pic, caption=loc.TEXT_AVA_READY, reply_markup=self.menu_kbd())
