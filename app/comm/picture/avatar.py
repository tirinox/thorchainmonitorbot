from PIL import Image, ImageOps

from lib.draw_utils import image_square_crop
from lib.utils import async_wrap

THOR_AVA_FRAME_PATH = './data/thor_ava_frame.png'
THOR_LASER_PATH = './data/laser_green_2.png'
THOR_LASER_SIZE = 24

MAX_SOURCE_SIDE = 2048  # the frame is 1024 px; a bigger source only costs memory and time


def combine_frame_and_photo(photo: Image.Image):
    frame = Image.open(THOR_AVA_FRAME_PATH)

    photo = photo.resize(frame.size).convert('RGBA')
    result = Image.alpha_composite(photo, frame)

    return result


def prepare_photo(photo: Image.Image) -> Image.Image:
    photo.draft(None, (MAX_SOURCE_SIDE, MAX_SOURCE_SIDE))  # JPEG: decode at a reduced scale right away
    photo = ImageOps.exif_transpose(photo)  # pictures sent as files often keep their rotation in EXIF only
    photo.thumbnail((MAX_SOURCE_SIDE, MAX_SOURCE_SIDE))
    return photo


@async_wrap
def make_avatar(photo: Image.Image):
    photo = image_square_crop(prepare_photo(photo))

    return combine_frame_and_photo(photo)


