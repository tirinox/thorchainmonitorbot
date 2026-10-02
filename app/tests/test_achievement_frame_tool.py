import pytest
from PIL import Image, ImageDraw

from tools.achievement_frame import find_hole


def _save(tmp_path, name, im):
    path = tmp_path / name
    im.save(path)
    return str(path)


def test_finds_the_hole_of_a_ring(tmp_path):
    im = Image.new('RGB', (512, 512))
    ImageDraw.Draw(im).ellipse((156, 140, 356, 340), outline=(220, 220, 220), width=40)
    x, y, r = find_hole(_save(tmp_path, 'ring.png', im))
    # the inner edge of the ring: radius 100 - 40 px out of 512, centered at (256, 240)
    assert (x, y) == (pytest.approx(0.5, abs=0.01), pytest.approx(240 / 512, abs=0.01))
    assert r == pytest.approx(60 / 512, abs=0.02)


@pytest.mark.parametrize('color', [(0, 0, 0), (240, 240, 240)])
def test_no_hole_is_none_not_a_crash(tmp_path, color):
    # no ray stops: all dark, or the middle is as bright as everything (the +50 threshold goes past white)
    path = _save(tmp_path, 'plain.png', Image.new('RGB', (512, 512), color))
    for brighter_by in (15, 30, 50):
        assert find_hole(path, brighter_by) is None
