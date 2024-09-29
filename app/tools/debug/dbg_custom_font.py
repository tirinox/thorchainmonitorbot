from comm.picture.sprite_font import SpriteFont
from tools.lib.lp_common import save_and_show_pic, LpAppFramework


def main():
    LpAppFramework.solve_working_dir_mess()
    font = SpriteFont('./data/achievement/numbers_runic')

    examples = [
        '$20K',
        '5',
        '100K R',
        '20M R',
        '500',
        'ETH', 'BNB', 'ATOM', 'DOGE', 'BTC', 'LTC', 'BCH', 'AVAX'
    ]

    for example in examples:
        pic = font.render_string(example)
        save_and_show_pic(pic, name=f'{example}.png')


if __name__ == '__main__':
    main()
