import json
import os

DEMO_DIR = os.path.dirname(os.path.abspath(__file__))


def _demo_files() -> dict:
    """Demo name => path to its JSON file; subfolders (e.g. the generated achievements/) are scanned too"""
    files = {}
    for root, _, names in os.walk(DEMO_DIR):
        for f in names:
            if f.endswith('.json'):
                files[f[:-5]] = os.path.join(root, f)
    return files


def load_demo(name: str) -> dict:
    """The whole demo: template_name, parameters and the optional meta (title, subtitle, lang, order)"""
    path = _demo_files().get(name)
    if not path:
        return {}
    with open(path) as f:
        return json.load(f)


def demo_template_parameters(name: str):
    demo = load_demo(name)
    if not demo:
        return None, None
    return demo['template_name'], demo['parameters']


def available_demo_templates():
    return list(_demo_files())
