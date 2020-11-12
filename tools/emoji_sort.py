import random

from services.notify.types.rune_price import emoji_for_percent_change


def main():
    with open('../misc/emoji_raw.txt') as f:
        lines = f.readlines()

    items = []
    for l in lines:
        comp = (' '.join(l.split())).split()
        if len(comp) == 3:
            _, percent, emoji = comp
            percent = float(percent[:-1])
            items.append((percent, emoji))

    items.sort()
    emj = [e[1] for e in items]
    unique_emj = list({s: 0 for s in emj})  # unique ordered

    print(*items, sep='\n')
    print(unique_emj)

    min_arr = []
    used = set()
    for v, emoji in items:
        if emoji not in used:
            used.add(emoji)
            min_arr.append((v, emoji))

    with open('../misc/emoji_sorted.txt', 'w') as f:
        print(*items, sep='\n', file=f)
        print([
            (0, emj) for emj in unique_emj
        ], file=f)
        print(min_arr)

def tests():
    for _ in range(50):
        x = random.uniform(5, 200)
        y = random.uniform(-x, x)
        r = emoji_for_percent_change(y)
        print(round(y * 10) / 10, r)

if __name__ == "__main__":
    main()
    tests()
