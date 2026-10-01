# Achievement card frames: design guide

Every achievement card (`app/renderer/templates/achievement.jinja2`, 1024×1024) is drawn over a **frame**: a painted
picture of a wreath, ring or other ornament with an empty dark hole in the middle where the milestone number goes.
This guide is how to make a new frame or repaint an old one so it fits the set.

## Where things live

| What | Where |
|---|---|
| Frame pictures | `app/data/renderer/static/img/achievement/bg/*.png` (1024×1024 RGB) |
| Frame constants (`BG_*`) and which achievement uses which frame (`background=`) | `app/jobs/achievement/ach_list.py` |
| Per-frame layout and colors (`WreathStyle`, `BACKGROUND_STYLE`) | `app/comm/picture/achievement_card.py` |
| Card template | `app/renderer/templates/achievement.jinja2` |
| Generate, measure and preview frames | `app/tools/achievement_frame.py` |
| Renderer gallery demos | `make renderer-demos`, then http://127.0.0.1:8404/render/demo |
| Checks (every frame exists, has a style, its base color matches its edges) | `app/tests/test_achievement_card.py` |

## Design rules

- **Each frame has its own idea and silhouette.** A frame names its category at a glance and must not look like any other frame. The set already has runic metal rings (BTC, ETH, RUNE), leafy wreaths, a flame vortex, a thorny lightning wreath, a vault door, a chain circle, two dragons, braided cords with a handshake, a fire ring and a balloon ring. A new frame takes a new shape: say in the prompt which shapes it must **not** be.
- **One palette per frame**, different from its neighbours. The palette also sets the `tint` (the glow of the number).
- **Painterly, premium, detailed:** fantasy digital art with real material depth, Norse/Celtic motifs where they fit. Never flat, cartoonish, plastic or icon-like.
- **No text, letters or numbers** in the picture. Symbols only when they are the point of the frame: ₿ on the BTC frame, the Ethereum crystal, ᚱ on the RUNE crystal, `$` on the stablecoin coins.
- A main object (anchor, tankards, handshake) is welcome, but it **sits right under the hole**, not at the bottom of the picture: the bottom of the card belongs to the title and the stats.

## What a frame picture must be

- Square, 1024×1024.
- One frame, centered horizontally, the center of its opening **a little above the middle**.
- The opening is a **clean, empty, almost black disc about a third of the picture wide**. The number is fitted into it.
- **Plain very dark background falling off to black at the edges.** Nothing touches the picture edges.
- The whole composition fits into the **upper ~85%** of the picture.

## Prompt template

Write the prompt fresh for every frame. Keep the layout and quality blocks; describe the frame itself in your own words.

```text
Paint an achievement frame for <CATEGORY> of the THORChain network: <what the records are about>.
It is one badge of a set where every frame has its own distinct shape, so this one must NOT be <shapes already used
that it could be confused with>, and must NOT have a medallion or crystal on top.

The frame: <shape, materials, ornament, the main object and where it sits: "just below the opening, close to it">.

Palette: <colors> against near-black; no <colors of the neighbouring frames>.

Layout (strict):
- Square picture; the frame is centered horizontally, the center of its opening a little above the exact middle.
- The opening is a clean, empty, almost black round space roughly one third of the picture wide.
  Keep it completely empty: a number will be added there later.
- The whole composition fits in the upper 85% of the picture; the lowest part stays empty and dark.
- Background: plain, very dark, falling off to black toward the edges; nothing touches the picture edges.

Lighting: <dramatic, cinematic, rim light of the palette colors>.

Quality: a premium, highly detailed painterly fantasy illustration with real material depth, like cinematic concept
art. Not cartoonish, not flat, not plastic, not a game UI icon, not clip-art.

Do not draw any text, letters, numbers or logos <except ...>.
```

- **Repainting an old frame:** pass the old picture as `--ref`, start with "Refresh this achievement frame (the reference image)", describe what it is (motifs, palette, silhouette) and ask to keep the idea but add detail and depth. Describe any change explicitly ("at the bottom, instead of the ribbon, two tankards...").
- **New frame:** pass **no** reference. The model copies the shape of whatever it is shown, so passing the runic rings brings back a runic ring.
- **A twin of an existing frame** (like BTC and ETH): pass that frame as the reference and say "make its twin, matching its scale, camera, lighting and finish".
- Too flat a result: strengthen the quality block with the materials ("forged metal with engraved filigree, scratches, worn polish, tarnish in the recesses; realistic reflections and ambient occlusion").

## Models

Through OpenRouter (`OPENROUTER_API_KEY` in `.env`):

- **`google/gemini-3-pro-image`, the default.** About $0.14 and 25 s per picture. Takes reference pictures well. It **ignores the reasoning effort**; only the `seed` changes the result, and the same seed gives the same picture.
- `openai/gpt-5.4-image-2`: about $0.25 and 2 min per picture. It uses the effort, but a higher effort did not give a better picture.

Make **three seeds** of one prompt and pick by looking at them **inside a card**, not alone.

## Workflow

All commands run from `app/` with `PYTHONPATH=.`. The preview needs the renderer: `make renderer-dev` or the `renderer` container.

1. **Generate** candidates:
   ```bash
   PYTHONPATH=. python tools/achievement_frame.py generate --prompt my_prompt.txt --name stables --seeds 1 2 3
   ```
   They land in `../temp/frames/`. Add `--ref nn_wreath_x.png` to repaint or twin a frame.
2. **Measure** them:
   ```bash
   PYTHONPATH=. python tools/achievement_frame.py measure ../temp/frames/stables_s*.png --overlay ../temp/frames
   ```
   It prints the hole at three thresholds, the base (edge) color and how far the ornament reaches, and draws the circles on copies.
3. **Preview** real cards:
   ```bash
   PYTHONPATH=. python tools/achievement_frame.py preview ../temp/frames/stables_s*.png --key stables_in_vault --tint '#8ff0c0'
   ```
   Use `--hole X Y R` and `--size/--top/--shade` to try the layout.
4. **Install** the chosen picture under a **new file name** (`nn_wreath_<category>.png`, or `_2`, `_3` when replacing). Never overwrite a file the renderer has served: its browser keeps the old picture cached. `git rm` the replaced file.
5. **Wire it in:**
   - a `BG_*` constant in `ach_list.py` and `background=BG_*` on the achievements;
   - a `WreathStyle` line in `BACKGROUND_STYLE` (see below).
6. **Check:**
   - `python -m pytest tests/test_achievement_card.py`;
   - `make renderer-demos`;
   - look at a few cards in EN and RU, including a long title and a long number.

## WreathStyle fields

| Field | What it is | How to set it |
|---|---|---|
| `tint` | Glow of the number and the date | A light color of the frame's palette |
| `hole_x`, `hole_y`, `hole_r` | The circle the number (with its "Over" label) is fitted into, as fractions of the picture size | `measure`, the **+30** line. If the three lines disagree, check the overlay and pick by eye: dark twigs, a glowing halo or an object reaching into the opening fool the rays. With an object in the opening, put a smaller circle in the free part above it |
| `base` | Picture edge color: the card is painted with it, so the picture flows into the card | `measure`, "base". A test checks it against the file |
| `size`, `top` | Where the picture sits on the card, px (default 860 and 40) | Make it smaller and lower when the ornament reaches the date line (top ~0.05) or something hangs low (bottom over ~0.85). The title starts at ~794 px |
| `shade_from` | Card height % where the shade under the title starts (default 58) | Raise to ~70 when a low object would be dimmed |

The picture fades into `base` at its edges (10%); there is no round mask any more, so ornament may reach far from the ring.

## The frames

| Constant | File | Idea | Palette |
|---|---|---|---|
| `BG_LIQUIDITY` | `nn_wreath_liquidity.png` | Celtic knotwork ring with ivory antlers, leaves, a knot shield-heart below | teal, jade, ivory |
| `BG_NETWORK` | `nn_wreath_network.png` | Braided wreath with feathers, a knot on top, a chevron shield and bronze rings | sage, muted teal, beige |
| `BG_SWAPS` | `nn_wreath_swaps.png` | Stone and steel ring in a whirl of turquoise flame with silver arrow-blades | cyan, electric blue |
| `BG_USERS` | `nn_wreath_users.png` | Thorny branch wreath charged with lightning, white crystal spikes | dark wood, green, electric blue |
| `BG_RUNE` | `nn_wreath_rune.png` | Gunmetal and obsidian runic ring, crystal with ᚱ, lightning | turquoise, green |
| `BG_REVENUE` | `nn_wreath_revenue_toast.png` | Harvest wreath of wheat, laurel and olive with coins, two tankards clashing below | gold, emerald |
| `BG_AFFILIATE` | `nn_wreath_affiliate_grip.png` | Braided leather cords with oath rings turning into two Viking forearms in a grip | leather brown, silver, gold |
| `BG_BURN` | `nn_wreath_burnt.png` | Wreath of branches and feathers in roaring fire over coals (for burnt RUNE, unused yet) | orange, amber, red |
| `BG_VAULT` | `nn_wreath_vault.png` | Bronze and steel vault door ring with bolts and amber lamps, icy spikes | bronze, amber, turquoise ice |
| `BG_STABLES` | `nn_wreath_stables_chains.png` | Rusted chipped iron chains with dollar coins, a big `$` coin locking them | rust, dark iron, dollar green |
| `BG_TRADE` | `nn_wreath_trade.png` | Gold and ruby dragons chasing each other, passing coins | gold, ruby |
| `BG_BTC` | `nn_wreath_btc_vault_2.png` | Bronze runic ring under a ₿ medallion | bronze, gold, orange |
| `BG_ETH` | `nn_wreath_eth_vault_2.png` | Silver runic ring under a violet Ethereum crystal (BTC's twin) | silver, violet |
| `BG_ANNIVERSARY` | `nn_wreath_ann_3.png` | Gold and turquoise runic ring among balloons, confetti and fireworks; balloon digits | gold, turquoise, festive |
