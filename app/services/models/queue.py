from dataclasses import dataclass


@dataclass
class QueueInfo:
    swap: int = 0
    outbound: int = 0
    internal: int = 0

    @classmethod
    def error(cls):
        return cls(-1, -1, -1)

    @property
    def is_ok(self):
        return self.swap >= 0 and self.outbound >= 0 and self.internal >= 0

    @property
    def is_full(self):
        return self.swap > 0 or self.outbound > 0
