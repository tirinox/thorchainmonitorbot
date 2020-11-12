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

    with open('../misc/emoji_sorted.txt', 'w') as f:
        print(*items, sep='\n', file=f)
        print(unique_emj, file=f)


if __name__ == "__main__":
    main()
