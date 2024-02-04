-- forked from 9bda51b5-c3ad-4ab6-abd8-17a004ace38d
WITH rewards AS (
  SELECT
    day,
    liquidity_fees,
    liquidity_fees_usd,
    block_rewards,
    block_rewards_usd,
    liquidity_fees * 100 / (liquidity_fees + block_rewards) AS pct_of_earnings_from_liq_fees,
    avg(pct_of_earnings_from_liq_fees) OVER(
      ORDER BY
        day ROWS BETWEEN 29 PRECEDING
        AND CURRENT ROW
    ) as pctday_moving_average_30d,
    total_earnings,
    total_earnings_usd,
    earnings_to_nodes,
    earnings_to_nodes_usd,
    earnings_to_pools,
    earnings_to_pools_usd,
    floor(avg_node_count) as node_count,
    ROW_NUMBER() OVER(
      ORDER BY
        day
    ) AS rownum
  from
    thorchain.defi.fact_daily_earnings
  WHERE
    day > dateadd(DD,-14,getdate())
),
cumulative_rewards AS(
  SELECT
    day,
    liquidity_fees,
    liquidity_fees_usd,
    block_rewards,
    block_rewards_usd,
    pct_of_earnings_from_liq_fees,
    CASE
      WHEN pctday_moving_average_30d > 0 THEN pctday_moving_average_30d
      ELSE 0
    END AS pct_30d_moving_average,
    total_earnings,
    total_earnings_usd,
    earnings_to_nodes,
    earnings_to_nodes_usd,
    earnings_to_pools,
    earnings_to_pools_usd,
    (
      SELECT
        SUM(liquidity_fees_usd)
      FROM
        rewards as b
      WHERE
        b.rownum <= a.rownum
    ) as liquidity_fees_usd_cumulative,
    (
      SELECT
        SUM(block_rewards_usd)
      FROM
        rewards as b
      WHERE
        b.rownum <= a.rownum
    ) as block_rewards_usd_cumulative,
    (
      SELECT
        SUM(total_earnings_usd)
      FROM
        rewards as b
      WHERE
        b.rownum <= a.rownum
    ) as total_earnings_usd_cumulative,
    (
      SELECT
        SUM(earnings_to_nodes_usd)
      FROM
        rewards as b
      WHERE
        b.rownum <= a.rownum
    ) as earnings_to_nodes_usd_cumulative,
    (
      SELECT
        SUM(earnings_to_pools_usd)
      FROM
        rewards as b
      WHERE
        b.rownum <= a.rownum
    ) as earnings_to_pools_usd_cumulative
  from
    rewards as a
)
select
  *
from
  cumulative_rewards
order by
  day DESC