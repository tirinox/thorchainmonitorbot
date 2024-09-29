from PIL import Image

from lib.draw_utils import image_square_crop
from lib.utils import async_wrap

THOR_AVA_FRAME_PATH = './data/thor_ava_frame.png'
THOR_LASER_PATH = './data/laser_green_2.png'
THOR_LASER_SIZE = 24


def combine_frame_and_photo(photo: Image.Image):
    frame = Image.open(THOR_AVA_FRAME_PATH)

    photo = photo.resize(frame.size).convert('RGBA')
    result = Image.alpha_composite(photo, frame)

    return result


@async_wrap
def make_avatar(photo: Image.Image):
    photo = image_square_crop(photo)

    return combine_frame_and_photo(photo)


