from dataclasses import dataclass


@dataclass
class QueueInfo:
    swap: int
    outbound: int

    @classmethod
    def error(cls):
        return cls(-1, -1)

    @property
    def is_ok(self):
        return self.swap >= 0 and self.outbound >= 0
