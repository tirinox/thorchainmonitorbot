-- forked from 498df68f-821b-41ce-b3c1-fe1a3ef2bf46
WITH unique_swappers AS (
  SELECT
    day,
    sum(unique_swapper_count) AS unique_swapper_count
  FROM
    thorchain.defi.fact_daily_pool_stats
  GROUP BY
    day
),
swap_transactions AS (
  SELECT
    max(block_timestamp) as block_timestamp,
    tx_id,
    max(from_amount_usd) as volume
  from
    thorchain.defi.fact_swaps
  group by
    tx_id
),
swap_count AS(
  SELECT
    to_date(block_timestamp) as day,
    COUNT(*) OVER(PARTITION BY day) AS swap_count
  from
    swap_transactions
),
grouped AS (
  SELECT
    day,
    avg(swap_count) as swap_count
  from
    swap_count
  group by
    day
),
joined AS (
  SELECT
    a.day,
    a.swap_count,
    unique_swapper_count
  FROM
    grouped AS a
    LEFT JOIN unique_swappers AS b on a.day = b.day
)
SELECT
  *,
  SUM(swap_count) OVER (
    ORDER BY
      day
  ) AS swap_count_cumulative
FROM
  joined
WHERE
  day is not null
ORDER BY
  day DESC