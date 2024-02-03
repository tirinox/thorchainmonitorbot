-- forked from 37de904e-a86d-4880-93bf-1affba6af82c
-- could be hourly
WITH full_volume as (
  SELECT
    max(to_date(block_timestamp)) as day,
    tx_id,
    max(from_amount_usd) as volume
  from
    thorchain.defi.fact_swaps
  group by
    tx_id
),
synth_volume as (
  SELECT
    max(to_date(block_timestamp)) as day,
    tx_id,
    max(from_amount_usd) as synth_volume
  from
    thorchain.defi.fact_swaps
  WHERE
    to_asset like '%/%'
    or from_asset like '%/%'
  group by
    tx_id
),
synth_volume_daily as (
  SELECT
    day,
    sum(synth_volume) as synth_volume
  from
    synth_volume
  group by
    day
),
full_volume_daily as (
  SELECT
    day,
    sum(volume) as volume
  from
    full_volume
  group by
    day
),
joined AS (
  SELECT
    a.day,
    COALESCE(synth_volume, 0) as synth_volume,
    COALESCE(a.volume, 0) as full_volume,
    ROW_NUMBER() OVER(
      ORDER BY
        a.day
    ) as rownum
  from
    full_volume_daily as a
    left join synth_volume_daily as b on a.day = b.day
),
culmulative AS (
  SELECT
    day,
    synth_volume as swap_synth_volume_usd,
    full_volume as swap_volume_usd,
    (
      SELECT
        SUM(full_volume)
      FROM
        joined as b
      WHERE
        b.rownum <= a.rownum
    ) as swap_volume_usd_cumulative
  FROM
    joined as a
)
SELECT
  day,
  swap_synth_volume_usd,
  (swap_volume_usd - swap_synth_volume_usd) as swap_non_synth_volume_usd,
  swap_volume_usd,
  swap_volume_usd_cumulative
FROM
  culmulative
WHERE
  day is not null
ORDER BY
  day DESC