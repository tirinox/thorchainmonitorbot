import json
from dataclasses import dataclass

from models.base import BaseModelMixin


@dataclass
class Model(BaseModelMixin):
    a: str = ''
    b: int = 5
    c: bool = True


def test_filter_args():
    m = Model('hello', 6, False)
    assert m.a == 'hello'
    assert str(m) == "Model(a='hello', b=6, c=False)"

    j = m.as_json_string
    assert j == '{"a":"hello","b":6,"c":false}'

    m2 = Model.from_json(j)
    assert m == m2

    jmod = json.loads(j)
    jmod['foo'] = 'spy'
    jmod['gg'] = '1'
    j3 = json.dumps(jmod)

    m3 = Model.from_json(j3)
    assert m3 == m
    # = json.loads(j)
