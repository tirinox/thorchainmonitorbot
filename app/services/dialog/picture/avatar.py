import logging
from typing import Optional

import face_recognition
import numpy as np
from PIL import Image, ImageDraw

from services.lib.draw_utils import image_square_crop
from services.lib.utils import async_wrap


class LaserEyeMask:
    def __init__(self, laser_mask='data/laser_green_2.png', size_p=15, debug=False):
        self.debug = debug
        self.size_p = size_p
        self.laser_eye_1 = Image.open(laser_mask).convert('RGBA')

    @staticmethod
    def center_of_feature(f):
        nt = np.array(f)
        x, y = np.mean(nt, axis=0)
        return int(x), int(y)

    def _apply_for_face(self, frame: Image.Image, face):
        lex, ley = self.center_of_feature(face['left_eye'])
        rex, rey = self.center_of_feature(face['right_eye'])

        if self.debug:
            draw = ImageDraw.Draw(frame)
            draw.ellipse((lex - 5, ley - 5, lex + 5, ley + 5), outline='red', width=2)
            draw.ellipse((rex - 5, rey - 5, rex + 5, rey + 5), outline='red', width=2)

        eye = self.laser_eye_1.copy()
        eye.thumbnail((int(frame.width / 100.0 * self.size_p),
                       int(frame.height / 100.0 * self.size_p)))
        frame.paste(eye, (lex - eye.width // 2, ley - eye.height // 2), mask=eye)
        frame.paste(eye, (rex - eye.width // 2, rey - eye.height // 2), mask=eye)

    def apply(self, frame):
        np_image = np.asarray(frame)

        np_image = np_image[:, :, :3]  # discard Alpha-channel

        face_landmarks_list = face_recognition.face_landmarks(np_image)

        logging.debug(f'{len(face_landmarks_list)} faces found.')

        for face in face_landmarks_list:
            self._apply_for_face(frame, face)
        return frame


THOR_AVA_FRAME_PATH = './data/thor_ava_frame.png'
THOR_LASER_PATH = './data/laser_green_2.png'
THOR_LASER_SIZE = 24

laser_masker: Optional[LaserEyeMask] = None


def combine_frame_and_photo(photo: Image.Image):
    frame = Image.open(THOR_AVA_FRAME_PATH)

    photo = photo.resize(frame.size).convert('RGBA')
    result = Image.alpha_composite(photo, frame)

    return result


@async_wrap
def make_avatar(photo: Image.Image, with_lasers=False):
    photo = image_square_crop(photo)

    if with_lasers:
        global laser_masker
        if not laser_masker:
            laser_masker = LaserEyeMask(THOR_LASER_PATH, THOR_LASER_SIZE)
        photo = laser_masker.apply(photo)

    return combine_frame_and_photo(photo)


if __name__ == '__main__':
    laser = LaserEyeMask()
    # image: Image.Image = Image.open('data/sample.png')
    image: Image.Image = Image.open('data/thor.jpeg')
    result = laser.apply(image)
    result.show()
