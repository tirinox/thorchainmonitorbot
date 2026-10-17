# Персональный трекер свапов — проект на одобрение

Цель: пользователь добавил кошелёк в «Мои кошельки» → каждый его свап бот ведёт от появления
во входящих до полной выплаты outbound (или refund), а если свап задерживается — объясняет, почему
(халт торговли/подписи/цепи, очередь outbound, подтверждения и т.п.).

## 1. Что уже есть и переиспользуется

| Нужно | Уже есть | Где |
|---|---|---|
| Начало свапа из блока (observed inbound / MsgDeposit, memo, сумма, assets) | `SwapStartDetectorFromBlock` → `AlertSwapStart` | `jobs/scanner/swap_start_detector.py` |
| События свапа в Redis (`swap`, `streaming_swap`, `scheduled_outbound`, `outbound`) и сборка `ThorAction` по завершении | `SwapExtractorBlock` + `EventDatabase` (`tx:tracker:{tx_id}`) + `SwapProps.build_action` | `jobs/scanner/swap_extractor.py`, `event_db.py`, `swap_props.py` |
| Стадии tx с thornode | `ThorConnector.query_tx_status` (`/thorchain/tx/status/{hash}`) — реализован, **никем не используется** | `api/aionode/connector.py:156` |
| Стриминг на advanced queue (в `/tx/status` его нет) | `/thorchain/swap/streaming/{hash}` → `StreamingSwap` (сейчас raw-вызов в `stream_watchlist.py:52`, переедет в коннектор) | `models/s_swap.py` |
| Квота (ожидаемый выход, ETA) | `query_swap_quote(..., height=)` как в `StreamingSwapStartTxNotifier` | `notify/public/s_swap_notify.py` |
| Mimir | `deps.mimir_const_holder.get_constant(name)` (обновляется каждые 130 с) | `models/mimir.py` |
| Состояние цепей (`halted`, `trading_paused`) | `deps.chain_info: ChainInfoHolder` (67 с) | `models/chains.py` |
| Очередь | `deps.queue_holder` (`/thorchain/queue`, 60 с) | `notify/public/queue_notify.py` |
| Высоты подписей по цепям | `deps.last_block_cache` → `ThorLastBlock.last_signed_out` | `jobs/fetch/cached/last_block.py` |
| Адрес ↔ пользователь | `UserWatchlist(db, category)` | `models/node_watchers.py` |
| Доставка личных сообщений на любую платформу, rate limit, пауза неактивных | `BasePersonalNotifier._send_message` / `broadcaster.safe_send_message_rate` | `notify/personal/base.py` |
| Картинка завершённого свапа | `AlertPresenter.render_swap_finish` (`swap_finished.jinja2`) | `notify/alert_presenter.py:460` |

Чего нет: подписки пользователя на конкретный tx, стадийной модели, диагностики задержек, текстов.

## 2. Архитектура

```
block_scanner ─► SwapStartDetectorFromBlock ─► PersonalSwapTracker.on_data(AlertSwapStart)
                                                   │  адреса из memo/from → SwapWatchlist → users?
                                                   │  да → SwapTrack в Redis + сообщение «Swap detected»
                                                   ▼
                       PersonalSwapTracker.fetch()  (BaseFetcher, каждые 20 с)
                         для каждого tx из SwapTrack:Active, у кого next_poll_ts <= now:
                           /thorchain/tx/status/{hash}  (+ /swap/streaming/{hash} если стриминг)
                           → SwapStage  ──изменилась──► сообщение стадии
                           → долго в стадии ──► SwapDelayDiagnoser(mimir, chain_info, queue, last_block)
                                                 ──диагноз изменился──► сообщение «delayed» / «resumed»
                           → DONE / REFUNDED ──► EventDatabase → SwapProps.build_action → финальное сообщение (+карточка)
                           → > give_up_after ──► «still pending», стоп
```

### 2.1 Файлы

- `notify/personal/swap_tracker.py` — `SwapWatchlist(UserWatchlist(db, 'SwapTracker'))`,
  `PersonalSwapTracker(BaseFetcher, INotified)`: `on_data` (старт), `fetch` (опрос), отправка через паттерн `BasePersonalNotifier`.
- `models/swap_track.py` — `SwapTrack` (dataclass ↔ JSON в Redis), `SwapStage`, `derive_stage(tx_status, streaming) -> StageInfo`,
  `diagnose(stage_info, ctx, waited, warn_after) -> Diagnosis | None`.
  Чистые функции без I/O → один тест `tests/test_swap_tracker_stages.py` на фикстурах `/tx/status`.
- `api/aionode/connector.py` — `query_streaming_swap(tx_id) -> StreamingSwap` (перенос raw-вызова из `stream_watchlist.py`).
- `models/mimir.py` — `MimirHolder.is_halt_active(key, thor_height)`: `0 < value <= height` (у `NodePauseChainGlobal` наоборот `value >= height`).
  Сейчас единственный читатель халтов (`chain_notify.py:132`) делает просто `bool(...)`, что неточно: в халт-мимирах лежит высота.
- `comm/dialog/my_wallets_menu.py` — кнопка «🔁 Track swaps ON/OFF» в настройках кошелька, `Props.PROP_TRACK_SWAPS`, включение при добавлении адреса, выключение при удалении. В отличие от баланса — для адресов **любой** цепи.
- `comm/localization/eng_base.py` (+ `rus.py`) — тексты из §4.
- `main.py` — вынести `SwapStartDetectorFromBlock` из-под `if notify_start`, подписать трекер, добавить в `tasks`.
- `example_config.yaml`:
  ```yaml
  personal:
    swap_tracker:
      enabled: true
      poll_period: 20s
      delay_warn_after: 10m      # сколько стадия должна «висеть» сверх ожидаемого, прежде чем писать ⚠️
      give_up_after: 24h
      max_active_per_user: 20    # защита от адресов арбитражных ботов
  ```

### 2.2 Привязка свапа к пользователю

При `AlertSwapStart` берём адреса: `from_address`, `memo.dest_address`, `memo.refund_address`
(не `AlertSwapStart.destination_address` — для observed inbound там адрес vault'а).
`SwapWatchlist.all_users_for_many_nodes(addresses)` → пользователи и их роль: **sender** / **recipient**.
Лимит-ордера (`memo.action == LIMIT_ORDER`) в MVP не трекаем (висят до TTL сутками).

Трекинг включён по умолчанию для добавленного кошелька (как бонд-трекер), выключается кнопкой. Адрес бота-арбитражёра
упрётся в `max_active_per_user` и в существующий `personal.rate_limit`.

### 2.3 Хранение

- `SwapTrack:{tx_id}` (hash, TTL 7 д): `users {user_id: role}`, `from_address`, `memo`, `in_asset`, `in_amount`, `out_asset`,
  `dest_address`, `start_height`, `started_ts`, `quote` (expected_out, total_sec), `stage`, `stage_since_ts`, `last_msg_ts`,
  `last_diag`, `last_diag_ts`, `next_poll_ts`, `streaming_reported_count`.
- `SwapTrack:Active` (set tx_id) — что опрашивать.
- События свапа и финальный `ThorAction` — из уже существующего `tx:tracker:{tx_id}` (`EventDatabase`), ничего не дублируем.

### 2.4 Стадии (`SwapStage`) из `/tx/status`

| Стадия | Условие | Что показываем |
|---|---|---|
| `OBSERVED` | `inbound_observed.completed`, `inbound_finalised` нет | подтверждения: `inbound_confirmation_counted.remaining_confirmation_seconds` |
| `SWAPPING` | `inbound_finalised.completed` и `swap_status.pending` | стриминг: `count/quantity`, своп-so-far (из `/swap/streaming/{hash}`; для legacy-очереди — из `swap_status.streaming`) |
| `OUTBOUND_DELAY` | `swap_finalised.completed`, `outbound_delay` есть и не completed | `remaining_delay_blocks/seconds` |
| `OUTBOUND_SIGNING` | `outbound_delay.completed`, `outbound_signed` не completed | `blocks_since_scheduled`; тут работает диагностика халтов |
| `DONE` | `outbound_signed.completed`; для RUNE/нативного выхода стадий outbound нет → `swap_finalised.completed` и `out_txs` непусто | итог из `ThorAction` |
| `REFUNDED` / `PARTIAL_REFUND` | `planned_out_txs[].refund` / `out_txs` с memo `REFUND:`; partial — если есть и OUT, и REFUND (стриминг) | причина — из Midgard (`/v2/actions?txid=`, `meta_refund.reason`), один запрос на финал; `refund`-события сканер не хранит |

Сообщение шлём только при **смене** стадии. Быстрый свап (RUNE→ETH за 12 с) даст два сообщения: «detected» и «completed»;
промежуточные стадии, проскочившие между опросами, не шлём. Стадию `OUTBOUND_SIGNING` отдельно не анонсируем
(она обычно длится секунды), только если застряла → через диагностику. Для стриминга дольше 10 мин — прогресс не чаще
раза в 10 мин.

Опрос: `next_poll_ts = now + 20 с` первые 5 мин, затем 60 с, после часа в одной стадии — 5 мин.

### 2.5 Диагностика задержки (`SwapDelayDiagnoser`)

Срабатывает, когда стадия висит дольше ожидаемого + `delay_warn_after` (ожидаемое: `remaining_confirmation_seconds`,
`remaining_delay_seconds`, `quote.total_swap_seconds`; для signing — 300 блоков `SigningTransactionPeriod`).
Правила по приоритету; первое совпавшее — причина. Повтор ⚠️ — только если причина изменилась или через час;
снятие причины → «resumed».

| Стадия | Проверка | Причина пользователю |
|---|---|---|
| любая | THORChain не производит блоки (`last_block_cache` старее 60 с) | сеть THORChain остановлена |
| `OBSERVED` | `Halt<SRC>Chain`, `SolvencyHalt<SRC>Chain`, `HaltChainGlobal`, `NodePauseChainGlobal`, `chain_info[src].halted` | наблюдение цепи X приостановлено, входящие не считаются |
| `OBSERVED` | `Halt<SRC>Trading` / `HaltTrading` | торговля X остановлена → после финализации будет refund |
| `OBSERVED` | подтверждения ещё идут | не ошибка: «ждём N подтверждений, ~T» |
| `SWAPPING` | `StreamingSwapPause` | стриминг-свапы на паузе, ваш ждёт |
| `SWAPPING` | `Halt<SRC|DST>Trading` / `HaltTrading` | торговля остановлена; на advanced queue свап ждёт, на legacy — refund |
| `OUTBOUND_DELAY` | `queue_holder.scheduled_outbound_value` велик | очередь outbound загружена ($X запланировано), это штатная задержка |
| `OUTBOUND_SIGNING` | `HaltSigning<DST>` / `HALTSIGNING` | подпись на цепи X остановлена операторами нод; outbound в очереди |
| `OUTBOUND_SIGNING` | `Halt<DST>Chain`, Solvency, Global, `chain_info[dst].halted` | цепь X остановлена |
| `OUTBOUND_SIGNING` | `last_signed_out[dst]` не двигается / `queue.outbound` большой | подписант цепи X отстаёт, очередь N tx |
| `OUTBOUND_SIGNING` | `blocks_since_scheduled > 300` | сеть переназначила outbound (vault без средств/газа); повтор каждые ~30 мин |
| иначе | — | причина неизвестна, сеть повторяет автоматически |

Факт из thornode, который надо помнить: `RUNE`/нативный выход никогда не имеет стадий `outbound_*`; после reschedule
`blocks_since_scheduled` считается от исходной высоты; при `MaxOutboundAttempts>0` recovery-свап получает **новый** tx id,
а исходный никогда не станет `completed` — поэтому есть `give_up_after`.

## 3. Чего в MVP нет (и когда добавить)

- `/track <txid>` без добавления кошелька — тот же `SwapTrack`, одноразовая подписка; добавить, если попросят.
- Лимит-ордера — когда будет понятно, что показывать сутками.
- Редактирование одного сообщения вместо новых (только Telegram) — если пользователи пожалуются на шум.
- Парсинг `failed_outbound_recovery` → переход на новый tx id — когда `MaxOutboundAttempts` станет > 0 в мейннете (сейчас 0).
- Картинка `swap_finished` на финал — дешёво (всё есть), включаю в MVP при `use_html_renderer`, но можно убрать.

## 4. Шаблоны сообщений (EN, Telegram HTML; RU — после одобрения)

Общие элементы: `👤` — адрес с THORName/локальным именем, `(you)` у адреса пользователя; ссылки `👁️‍🗨️Track` =
`track.thorchain.org/{tx}`, `🔍runescan`; суммы через `short_money`, время через `seconds_human`.

**1. Swap detected** (роль sender):
```
🔁 <b>Swap detected</b>
<b>0.5 BTC</b> ($52,400) → ⚡ → <b>ETH</b>
From: 👤bc1q…x7f2 (you)  →  To: 👤0x12…9a8c
Expected: ~<b>18.4 ETH</b> · est. time ~25 min
Streaming: 10 swaps, 1 block apart
⏳ Waiting for 2 confirmations on Bitcoin (~20 min)
Transaction: 👁️‍🗨️Track | 🔍runescan
```
Роль recipient — заголовок `📥 <b>Incoming swap</b>` и `(you)` у получателя. Если подтверждений не нужно (Cosmos, RUNE) —
строки ⏳ нет. Если квота не получена — нет строки Expected.

**2. Swapping** (только стриминг; не стриминг идёт сразу в 3/5):
```
🌊 <b>Swapping</b> · 4 of 10 swaps done
0.2 BTC → 7.36 ETH so far · ~36 s left
Transaction: 👁️‍🗨️Track
```

**3. Outbound scheduled:**
```
📤 <b>Swapped, sending</b>
You'll receive ~<b>18.37 ETH</b> at 👤0x12…9a8c
Outbound delay ~<b>12 min</b> (120 blocks) — the network throttles outbounds by value
Transaction: 👁️‍🗨️Track
```

**4. Delayed** (⚠️ раз на причину, не чаще раза в час):
```
⚠️ <b>Your swap is delayed</b> · outbound pending for 42 min
Reason: 🛑 Outbound signing on <b>Ethereum</b> is halted by node operators (HALTSIGNINGETH, 35 min ago).
Your 18.37 ETH is queued and will be sent when signing resumes. Nothing to do on your side.
Transaction: 👁️‍🗨️Track | 🔍runescan
```
Варианты строки Reason:
- `🛑 <b>Bitcoin</b> chain is halted (HALTBTCCHAIN); inbound transactions are not observed until it resumes.`
- `🛑 Trading on <b>Bitcoin</b> is halted; your swap will be refunded once the inbound is finalised.`
- `⏸ Streaming swaps are paused network-wide (STREAMINGSWAPPAUSE); yours will continue when unpaused.`
- `🚦 The outbound queue is busy: $1.2M scheduled ahead of you. This is a normal delay.`
- `🐢 The <b>Ethereum</b> signer is behind: 37 outbounds are waiting, last signed 25 min ago.`
- `🔁 The network has rescheduled your outbound (the vault may be short of funds or gas); it retries every ~30 min.`
- `🛑 THORChain has not produced a block for 8 min.`
- `❔ No known reason. The network retries automatically; usually this resolves itself.`

Снятие причины:
```
✅ Signing on <b>Ethereum</b> has resumed — your outbound should be sent shortly.
```

**5. Completed** (+ карточка `swap_finished` при включённом рендерере):
```
✅ <b>Swap completed</b> in 27 min
<b>0.5 BTC</b> ($52,400) → ⚡ → <b>18.37 ETH</b> ($52,110)
Fees: liquidity 0.21% · affiliate 0.1% (ll) · outbound 0.0012 ETH
Received at 👤0x12…9a8c (you)
Transactions: in 🔍runescan · out 🔍etherscan
```

**6. Refunded:**
```
↩️ <b>Swap refunded</b>
<b>0.5 BTC</b> → back to 👤bc1q…x7f2 (you), minus 0.0003 BTC outbound fee
Reason: <pre>emit asset 18.1 ETH less than price limit 18.3 ETH</pre>
Transactions: in 🔍runescan · refund 🔍mempool
```
Частичный (стриминг): `↩️ <b>Swap partially refunded</b>` + `Swapped 0.4 BTC → 14.7 ETH; 0.1 BTC returned.`

**7. Give up:**
```
🕰 <b>Still pending after 24 h</b> — I stop tracking it.
Last known state: outbound to Ethereum scheduled, not signed.
Check: 👁️‍🗨️Track | 🔍runescan. If it does not resolve, ask in THORChain Discord #support.
```

## 5. Решения (приняты 2026-10-17)

1. Трекинг свапов **включён по умолчанию** для каждого добавленного кошелька (как бонд) — да.
2. Входящие свапы (пользователь — получатель) трекаем — да.
3. Каждая стадия — новое сообщение (работает на всех платформах) — да, без редактирования.
4. Картинка `swap_finished` на финал — в MVP, при `use_html_renderer`.
5. RU-локализация — сразу вместе с EN.

Отложено: `/track <txid>` (напомнить), лимит-ордера, `failed_outbound_recovery`, редактирование сообщений.
