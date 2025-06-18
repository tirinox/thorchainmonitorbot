import yaml


FILE = "data/aff_compare.yaml"

def load():
    with open(FILE, "r", encoding="utf-8") as file:
        return yaml.load(file, Loader=yaml.FullLoader)


def save(data):
    with open(FILE, "w", encoding="utf-8") as file:
        yaml.dump(data, file, default_flow_style=False, allow_unicode=True)


def main():
    data = load()

    common_dict = {}
    for key, data in data.items():
        if 'affiliates' in data:
            affiliates = data['affiliates']
            print(f"{key} has {len(affiliates)} affiliates")
            common_dict = {**common_dict, **affiliates}

    print(f"Common affiliates count: {len(common_dict)}")

    data['common'] = {'affiliates': common_dict}

    save(data)

    #
    # struct = {
    #     'foo': {
    #         'affiliates': keys
    #     }
    # }
    #
    # # export to Yaml
    # with open("data/aff-list.yaml", "w", encoding="utf-8") as file:
    #     yaml.dump(struct, file, default_flow_style=False, allow_unicode=True)


if __name__ == "__main__":
    main()
