-- forked from Polaris_9R / Top 5 Swap Pairs (By Volume USD) @ https://flipsidecrypto.xyz/Polaris_9R/q/2023-03-31-04-19-pm-lR-Kch
-- todo: last 14 days pleaase
-- '{{start_date}}'::DATE
-- '{{end_date}}'::DATE + INTERVAL '1 DAY'
WITH tx_ids AS (
  SELECT
    TX_ID,
    COUNT(1) AS TX_COUNT,
    COUNT(DISTINCT POOL_NAME) AS POOL_COUNT
  FROM
    thorchain.defi.fact_swaps_events
  WHERE
    BLOCK_TIMESTAMP >= GETDATE() - Interval '7 day'
    AND BLOCK_TIMESTAMP < GETDATE() + Interval '1 day'
  GROUP BY
    1
),
refunds AS (
  SELECT
    TX_ID,
    COUNT(1) AS TX_COUNT
  FROM
    thorchain.defi.fact_refund_events
  WHERE
    BLOCK_TIMESTAMP >= GETDATE() - Interval '7 day'
    AND BLOCK_TIMESTAMP < GETDATE() + Interval '1 day'
  GROUP BY
    1
),
base AS (
  SELECT
    DISTINCT se.TX_ID,
    FIRST_VALUE(
      UPPER(
        SPLIT_PART(REPLACE(se.FROM_ASSET, '/', '.'), '-', 1)
      )
    ) OVER (
      PARTITION BY se.TX_ID
      ORDER BY
        s.FROM_AMOUNT_USD DESC
    ) AS FROM_ASSET,
    UPPER(
      SPLIT_PART(
        REPLACE(SPLIT_PART(se.MEMO, ':', 2), '/', '.'),
        '-',
        1
      )
    ) AS TO_ASSET,
    FIRST_VALUE(s.FROM_AMOUNT_USD) OVER (
      PARTITION BY se.TX_ID
      ORDER BY
        s.FROM_AMOUNT_USD DESC
    ) AS TOTAL_VOLUME_USD,
    COALESCE(
      1.0 * s.AFFILIATE_FEE_BASIS_POINTS / 1e4 * TOTAL_VOLUME_USD,
      0
    ) AS AFFILIATE_FEE_USD
  FROM
    thorchain.defi.fact_swaps_events AS se
    JOIN thorchain.defi.fact_swaps AS s ON se.TX_ID = s.TX_ID
    AND se.FROM_ASSET = s.FROM_ASSET
    AND se.TO_ASSET = s.TO_ASSET
    JOIN tx_ids AS t ON se.TX_ID = t.TX_ID
  WHERE
    se.TX_ID NOT IN (
      SELECT
        TX_ID
      FROM
        refunds
    )
    AND se.FROM_ASSET <> SPLIT_PART(se.MEMO, ':', 2)
    AND (
      CASE
        WHEN t.TX_COUNT > 1
        AND t.POOL_COUNT > 1 THEN se.FROM_ASSET <> 'THOR.RUNE'
        ELSE TRUE
      END
    )
    AND se.BLOCK_TIMESTAMP >= GETDATE() - Interval '7 day'
    AND se.BLOCK_TIMESTAMP < GETDATE() + Interval '1 day'
)
SELECT
  LEAST(FROM_ASSET, TO_ASSET) || ' <-> ' || GREATEST(FROM_ASSET, TO_ASSET) AS SWAP_PATH,
  SUM(TOTAL_VOLUME_USD) AS TOTAL_VOLUME_USD,
  cast(getdate() as Date) as day -- SUM(AFFILIATE_FEE_USD) AS AFFILIATE_FEE_USD
FROM
  base
GROUP BY
  1
ORDER BY
  2 DESC
LIMIT
  5