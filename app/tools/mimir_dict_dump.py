import yaml

from services.lib.texts import sep
from services.models.mimir_naming import DICT_WORDS_SORTED, BLOCK_CONSTANTS, BOOL_CONSTANTS, RUNE_CONSTANTS, \
    DOLLAR_CONSTANTS, BASIS_POINTS_CONSTANTS, TRANSLATE_MIMIRS, MIMIR_DICT_FILENAME, WORD_TRANSFORM


def compile_mimir_dict():
    print(f"Loaded {len(DICT_WORDS_SORTED)} words.")
    structure = {
        'words': DICT_WORDS_SORTED,
        'types': {
            'block': list(BLOCK_CONSTANTS),
            'bool': list(BOOL_CONSTANTS),
            'rune': list(RUNE_CONSTANTS),
            'usd': list(DOLLAR_CONSTANTS),
            'basis_points': list(BASIS_POINTS_CONSTANTS),
        },
        'word_transform': WORD_TRANSFORM,
        'translate': TRANSLATE_MIMIRS,
    }
    return structure


def main():
    structure = compile_mimir_dict()
    # save to yaml
    with open(MIMIR_DICT_FILENAME, 'w') as f:
        data = yaml.dump(structure, allow_unicode=True)
        f.write(data)


if __name__ == '__main__':
    main()
