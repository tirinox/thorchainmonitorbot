-- forked from 56576ba9-906f-4e73-83ef-bc0e4024d752
SELECT
  day,
  total_value_pooled,
  total_value_pooled_usd,
  total_value_bonded,
  total_value_bonded_usd,
  total_value_locked,
  total_value_locked_usd
FROM
  thorchain.defi.fact_daily_tvl
ORDER BY
  day DESC