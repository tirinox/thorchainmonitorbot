import asyncio
import random
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image
from aiogram.types import PhotoSize

from comm.dialog import avatar_picture_dialog as ava_module
from comm.dialog.avatar_picture_dialog import AvatarDialog, largest_size
from comm.localization.eng_base import EnglishLocalization
from comm.picture.avatar import make_avatar, prepare_photo, MAX_SOURCE_SIDE
from lib.config import Config

EXIF_ORIENTATION = 0x0112
ROTATED_90_CW = 6  # the camera was held sideways: the stored image must be turned to be seen upright


def _jpeg(size, orientation=None) -> Image.Image:
    im = Image.new('RGB', size, 'red')
    exif = Image.Exif()
    if orientation:
        exif[EXIF_ORIENTATION] = orientation
    buf = BytesIO()
    im.save(buf, 'JPEG', exif=exif)
    buf.seek(0)
    return Image.open(buf)  # lazy, as a downloaded picture


def _size(side):
    return PhotoSize(file_id=f'id{side}', file_unique_id=f'u{side}', width=side, height=side)


def test_largest_size_whatever_the_order():
    sizes = [_size(90), _size(320), _size(800), _size(1280)]
    assert largest_size(sizes).width == 1280
    random.shuffle(sizes)
    assert largest_size(sizes).width == 1280


def test_exif_rotation_is_applied():
    assert prepare_photo(_jpeg((300, 200), ROTATED_90_CW)).size == (200, 300)
    assert prepare_photo(_jpeg((300, 200))).size == (300, 200)


def test_big_picture_is_scaled_down():
    photo = prepare_photo(_jpeg((4000, 3000)))
    assert max(photo.size) <= MAX_SOURCE_SIDE
    assert photo.size[0] / photo.size[1] == pytest.approx(4 / 3, rel=0.01)


@pytest.mark.asyncio
@pytest.mark.parametrize('side', [90, 1280, 4000])
async def test_avatar_is_always_1024(side):
    avatar = await make_avatar(_jpeg((side, side)))
    assert avatar.size == (1024, 1024)


class FakeMessage:
    def __init__(self, **fields):
        self.__dict__.update(fields)
        self.chat = SimpleNamespace(id=42)
        self.answers = []

    async def answer(self, text, **_kwargs):
        self.answers.append(text)

    async def answer_document(self, _document, caption=None, **_kwargs):
        self.answers.append(caption)


def _dialog():
    dialog = AvatarDialog.__new__(AvatarDialog)  # skip __init__: it needs the bot and the FSM storage
    dialog.loc = EnglishLocalization(Config(name='./tests/test_config.yaml'))
    dialog.handled = []

    async def handle(message, loc, explicit_picture=None):
        dialog.handled.append(explicit_picture)

    dialog.handle_avatar_picture = handle
    return dialog


@pytest.mark.asyncio
async def test_photo_uses_the_largest_size():
    dialog = _dialog()
    await dialog.on_picture(FakeMessage(photo=[_size(90), _size(320), _size(1280)]))
    assert [p.width for p in dialog.handled] == [1280]


@pytest.mark.asyncio
@pytest.mark.parametrize('mime, size, accepted, answer', [
    ('image/jpeg', 3_000_000, True, None),
    ('application/pdf', 3_000_000, False, 'TEXT_AVA_ERR_INVALID'),
    (None, 3_000_000, False, 'TEXT_AVA_ERR_INVALID'),
    ('image/png', 50_000_000, False, 'TEXT_AVA_ERR_TOO_BIG'),
])
async def test_picture_files_are_checked(mime, size, accepted, answer):
    dialog = _dialog()
    message = FakeMessage(document=SimpleNamespace(mime_type=mime, file_size=size))
    await dialog.on_picture_doc(message)
    assert bool(dialog.handled) is accepted
    assert message.answers == ([getattr(dialog.loc, answer)] if answer else [])


def _working_dialog(monkeypatch, picture, make):
    dialog = AvatarDialog.__new__(AvatarDialog)
    dialog.loc = EnglishLocalization(Config(name='./tests/test_config.yaml'))

    async def sticker(_message, remove_keyboard=False):
        async def delete():
            pass
        return SimpleNamespace(delete=delete)

    async def download(_photo):
        return picture

    dialog.answer_loading_sticker = sticker
    monkeypatch.setattr(ava_module, 'download_tg_photo', download)
    monkeypatch.setattr(ava_module, 'make_avatar', make)
    return dialog


@pytest.mark.asyncio
async def test_too_many_pixels(monkeypatch):
    made = []

    async def make(photo):
        made.append(photo)

    huge = SimpleNamespace(size=(8000, 6000))  # 48 MP: only the header is read before the check
    dialog = _working_dialog(monkeypatch, huge, make)
    message = FakeMessage()
    await dialog.handle_avatar_picture(message, dialog.loc, explicit_picture=object())
    assert message.answers == [dialog.loc.TEXT_AVA_ERR_TOO_BIG]
    assert made == []


@pytest.mark.asyncio
async def test_at_most_two_avatars_at_once(monkeypatch):
    running, peak = 0, 0

    async def make(_photo):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.05)
        running -= 1
        return Image.new('RGBA', (8, 8))

    small = Image.new('RGB', (64, 64))
    jobs = []
    for _ in range(5):
        dialog = _working_dialog(monkeypatch, small, make)  # a new dialog per update, as in the bot
        jobs.append(dialog.handle_avatar_picture(FakeMessage(), dialog.loc, explicit_picture=object()))
    await asyncio.gather(*jobs)
    assert peak == 2
