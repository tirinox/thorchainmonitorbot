from .foo import demo_foo_parameters
from .rune_burn_and_income import demo_rune_burn_and_income_parameters

_TABLE = {
    "foo": demo_foo_parameters,
    "rune_burn_and_income": demo_rune_burn_and_income_parameters,
}


def demo_template_parameters(name: str):
    f = _TABLE.get(name)
    name, params = f() if f else (None, None)
    return name, params


def available_demo_templates():
    return ", ".join(list(_TABLE.keys()))
