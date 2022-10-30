from services.lib.draw_utils import CacheGrid


def test_grid_box():
    g = CacheGrid(4, 4)

    box1 = ((10, 10), (40, 19))
    g.fill_box(box1)
    assert g.is_box_occupied(box1)
    assert not g.is_box_occupied([(0, 0), (5, 6)])
