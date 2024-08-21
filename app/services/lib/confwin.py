from collections import deque


class ConfidenceWindow:
    def __init__(self, size=10, threshold=0.5):
        # make queue of size
        self.size = size
        self.queue = deque(maxlen=size)
        self.threshold = threshold

    def clear(self):
        self.queue.clear()

    def append(self, *rest):
        for v in rest:
            self.queue.append(v)

    def dominance_of(self, value):
        if len(self.queue) == 0:
            return 0.0
        d = sum(1 for v in self.queue if v == value) / len(self.queue)
        return d

    def most_common(self, check_threshold=False):
        if len(self.queue) == 0:
            return None
        best_fit = max(set(self.queue), key=self.queue.count)
        if check_threshold:
            return best_fit if self.dominance_of(best_fit) >= self.threshold else None
        else:
            return best_fit

    def contains(self, value):
        return self.dominance_of(value) >= self.threshold

    def __contains__(self, item):
        return self.contains(item)

    def __len__(self):
        return len(self.queue)
