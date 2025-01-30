import re
import yaml


def load_keys_from_file(filepath):
    key_dict = {}
    with open(filepath, "r", encoding="utf-8") as file:
        for line in file:
            match = re.match(r"([\w,]+):\s*\"([^\"]+)\"", line.strip())
            if match:
                keys = match.group(1).split(",")
                name = match.group(2)
                for key in keys:
                    key_dict[key.strip().lower()] = name
    return key_dict


def main():
    keys = load_keys_from_file("aff-list.txt")
    print(keys)

    struct = {
        'foo': {
            'affiliates': keys
        }
    }

    # export to Yaml
    with open("aff-list.yaml", "w", encoding="utf-8") as file:
        yaml.dump(struct, file, default_flow_style=False, allow_unicode=True)



if __name__ == "__main__":
    main()
