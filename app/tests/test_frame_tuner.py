import json

import pytest

from comm.picture.achievement_card import BACKGROUND_STYLE, WreathStyle
from renderer.frames import clean_style, load_styles, save_style, tuner_catalog, FIELDS, STYLE_FILE, CARD_PARAMETERS

STYLE = {'tint': '#ffcf7a', 'hole_x': 0.512, 'hole_y': 0.436, 'hole_r': 0.186, 'base': '#06080e',
         'size': 860, 'top': 40, 'shade_from': 58}


def test_style_file_is_as_the_tuner_writes_it():
    # the bot and the tuner read the same file: every frame has all the fields, already clean
    for frame, style in load_styles().items():
        assert clean_style(style) == style, frame
        assert set(WreathStyle._fields) <= set(style), frame
        assert set(style) <= set(FIELDS), frame
    assert set(BACKGROUND_STYLE) == set(load_styles(STYLE_FILE))


def test_card_parameters_are_the_style_fields():
    assert set(CARD_PARAMETERS) == set(WreathStyle._fields)


def test_clean_style_rounds():
    raw = {**STYLE, 'tint': ' #FFCF7A ', 'hole_x': '0.51249', 'size': 860.4, 'note': '  by   eye '}
    assert clean_style(raw) == {**STYLE, 'hole_x': 0.512, 'note': 'by eye'}
    assert 'note' not in clean_style({**STYLE, 'note': '  '})


@pytest.mark.parametrize('patch', [
    {'tint': 'red'},
    {'base': '#12345'},
    {'hole_r': 0.9},
    {'hole_x': 'nan'},
    {'size': None},
    {'shade_from': 101},
])
def test_clean_style_rejects(patch):
    with pytest.raises(ValueError):
        clean_style({**STYLE, **patch})


def _setup(tmp_path):
    bg = tmp_path / 'bg'
    bg.mkdir()
    for f in ('old.png', 'other.png', 'fresh.png'):
        (bg / f).write_bytes(b'')
    styles = tmp_path / 'frames.json'
    styles.write_text(json.dumps({'old.png': STYLE, 'other.png': STYLE}))
    demos = tmp_path / 'demo'
    (demos / 'achievements').mkdir(parents=True)

    def demo(name, template, background, tint):
        params = {'background': background, 'tint': tint, 'hole_x': 0.5, 'frame_size': 860, 'title': name}
        (demos / 'achievements' / f'{name}.json').write_text(
            json.dumps({'template_name': template, 'meta': {'title': name, 'lang': 'en'}, 'parameters': params}))

    demo('on_old', 'achievement.jinja2', 'old.png', STYLE['tint'])
    demo('own_tint', 'achievement.jinja2', 'old.png', '#abcdef')
    demo('on_other', 'achievement.jinja2', 'other.png', STYLE['tint'])
    demo('not_achievement', 'price.jinja2', 'old.png', STYLE['tint'])
    return dict(style_path=str(styles), bg_dir=str(bg), demo_dir=str(demos))


def _params(paths, name):
    with open(f"{paths['demo_dir']}/achievements/{name}.json") as f:
        return json.load(f)['parameters']


def test_save_style_patches_the_demos_of_the_frame(tmp_path):
    paths = _setup(tmp_path)
    new = {**STYLE, 'tint': '#00ff00', 'hole_y': 0.44, 'size': 800}
    saved, demos = save_style('old.png', new, **paths)

    assert saved == new
    assert demos == ['on_old', 'own_tint']
    assert load_styles(paths['style_path'])['old.png'] == new

    p = _params(paths, 'on_old')
    assert (p['tint'], p['hole_y'], p['frame_size'], p['base_color']) == ('#00ff00', 0.44, 800, '#06080e')
    assert p['title'] == 'on_old'
    # an achievement with a tint of its own keeps it, the rest of the style comes
    assert _params(paths, 'own_tint')['tint'] == '#abcdef'
    assert _params(paths, 'own_tint')['hole_y'] == 0.44
    assert _params(paths, 'on_other')['hole_x'] == 0.5
    assert _params(paths, 'not_achievement')['hole_x'] == 0.5

    # saving it again changes nothing
    assert save_style('old.png', new, **paths)[1] == []


def test_save_style_of_a_new_frame_goes_last(tmp_path):
    paths = _setup(tmp_path)
    save_style('fresh.png', STYLE, **paths)
    assert list(load_styles(paths['style_path'])) == ['old.png', 'other.png', 'fresh.png']


@pytest.mark.parametrize('frame', ['missing.png', '../frames.json', 'old'])
def test_save_style_only_for_a_frame_picture(tmp_path, frame):
    paths = _setup(tmp_path)
    with pytest.raises(ValueError):
        save_style(frame, STYLE, **paths)


def test_tuner_catalog_puts_new_pictures_first(tmp_path):
    paths = _setup(tmp_path)
    catalog = tuner_catalog(**paths)
    assert [f['file'] for f in catalog['frames']] == ['fresh.png', 'old.png', 'other.png']
    assert catalog['frames'][0]['style'] is None
    assert catalog['frames'][1]['users'] == ['on_old', 'own_tint']
    assert {d['name'] for d in catalog['demos']} == {'on_old', 'own_tint', 'on_other'}
