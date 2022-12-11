import math

from services.lib.delegates import WithDelegates, INotified
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger


class Milestones:
    MILESTONE_DEFAULT_PROGRESSION = [1, 2, 5]

    def __init__(self, progression=None):
        self.progression = progression or self.MILESTONE_DEFAULT_PROGRESSION

    def milestone_nearest(self, x, before: bool):
        progress = self.progression
        x = int(x)
        if x <= 0:
            return self.progression[0]

        mag = 10 ** int(math.log10(x))
        if before:
            delta = -1
            mag *= 10
        else:
            delta = 1
        i = 0

        while True:
            step = progress[i]
            y = step * mag
            if before and x >= y:
                return y
            if not before and x < y:
                return y
            i += delta
            if i < 0:
                i = len(progress) - 1
                mag //= 10
            elif i >= len(progress):
                i = 0
                mag *= 10

    def milestone_next(self, x):
        return self.milestone_nearest(x, before=False)

    def milestone_prev(self, x):
        return self.milestone_nearest(x, before=True)


class AchievementsTracker(WithLogger, WithDelegates, INotified):
    async def on_data(self, sender, data):
        pass

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

    def feed_data(self, value: int, name: str):
        self.notify(self, data)
