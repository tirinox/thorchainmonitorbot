from services.dialog.picture.custom_numbers import CustomNumbersFont
from tools.lib.lp_common import save_and_show_pic, LpAppFramework


def main():
    LpAppFramework.solve_working_dir_mess()
    font = CustomNumbersFont('./data/achievement/numbers_runic')

    examples = [
        '$20K',
        '5',
        '100K R',
        '20M R',
        '500'
    ]

    for example in examples:
        pic = font.render_string(example)
        save_and_show_pic(pic, name=f'{example}.png')


if __name__ == '__main__':
    main()
