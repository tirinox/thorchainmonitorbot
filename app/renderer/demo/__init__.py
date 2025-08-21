import json
import os.path


def demo_template_parameters(name: str):
    # path = current file path + name.json
    path = os.path.join(os.path.dirname(__file__), f"{name}.json")

    try:
        with open(os.path.join(path)) as f:
            data = json.load(f)
            return data['template_name'], data['parameters']
    except FileNotFoundError:
        return None, None


def available_demo_templates():
    # list all json files in the current directory
    path = os.path.join(os.path.dirname(__file__))
    files = [f for f in os.listdir(path) if f.endswith('.json')]
    # cut the .json suffix
    return [f[:-5] for f in files]
