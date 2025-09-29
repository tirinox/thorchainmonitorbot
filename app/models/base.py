from dataclasses import dataclass, asdict
from typing import Annotated

import ujson
from pydantic import BeforeValidator

from lib.utils import filter_kwargs_according_function_signature


@dataclass
class BaseModelMixin:
    @property
    def as_json_string(self):
        return ujson.dumps(asdict(self))

    @classmethod
    def from_json(cls, jstr):
        if not jstr:
            return None
        d = ujson.loads(jstr)
        try:
            filtered_d = filter_kwargs_according_function_signature(d, cls, 0)
            # noinspection PyArgumentList
            return cls(**filtered_d)
        except TypeError:  # Unexpected keyword
            return cls()


IntFromStr = Annotated[int, BeforeValidator(int)]
FloatFromStr = Annotated[float, BeforeValidator(float)]
